"""Telegram handlers that proxy requests to the Agentic RAG API."""

import logging
from typing import Any

from paperforge.core.config import TelegramSettings
from paperforge.schemas.agentic import AgenticRAGResponse
from paperforge.services.telegram.client import PaperforgeAPIClient

logger = logging.getLogger(__name__)


def split_message(value: str, limit: int) -> list[str]:
    """Split text without exceeding Telegram's message-size limit."""

    text = value.strip()
    if not text:
        return [""]
    parts: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts


def format_agentic_response(response: AgenticRAGResponse) -> str:
    """Format an answer, sources, and concise workflow metadata as plain text."""

    lines = [response.answer.strip()]
    if response.sources:
        lines.extend(["", "Sources:"])
        for source in response.sources[:5]:
            lines.append(f"[{source.citation}] {source.title}\n{source.pdf_url}")
    lines.extend(
        [
            "",
            (
                f"Status: {response.status}; search: {response.search_mode}; "
                f"attempts: {response.retrieval_attempts}; trace: {response.trace_id or 'disabled'}"
            ),
        ]
    )
    return "\n".join(lines)


class TelegramBot:
    """Build and run one long-polling bot instance in its own container."""

    def __init__(self, settings: TelegramSettings, api: PaperforgeAPIClient) -> None:
        self.settings = settings
        self.api = api

    def run(self) -> None:
        """Start polling and block until the process receives a shutdown signal."""

        if not self.settings.configured:
            raise RuntimeError("Telegram is disabled or PAPERFORGE_TELEGRAM__BOT_TOKEN is missing")
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters

        assert self.settings.bot_token is not None
        application = (
            Application.builder()
            .token(self.settings.bot_token.get_secret_value())
            .post_shutdown(self._post_shutdown)
            .build()
        )
        application.add_handler(CommandHandler("start", self._start))
        application.add_handler(CommandHandler("help", self._help))
        application.add_handler(CommandHandler("status", self._status))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._question))
        application.add_error_handler(self._error)
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=self.settings.drop_pending_updates,
        )

    async def _start(self, update: Any, context: Any) -> None:
        del context
        await update.effective_message.reply_text(
            "Paperforge is ready. Send an academic CS/AI research question.\n"
            "Commands: /status, /help"
        )

    async def _help(self, update: Any, context: Any) -> None:
        del context
        await update.effective_message.reply_text(
            "Ask about indexed arXiv computer-science papers. The agent checks scope, "
            "retrieves chunks, grades relevance, may rewrite once, then answers with sources."
        )

    async def _status(self, update: Any, context: Any) -> None:
        del context
        healthy = await self.api.healthy()
        await update.effective_message.reply_text(
            "Paperforge API is healthy." if healthy else "Paperforge API is unavailable."
        )

    async def _question(self, update: Any, context: Any) -> None:
        del context
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        if message is None or user is None or chat is None or not message.text:
            return
        if self.settings.allowed_user_ids and user.id not in self.settings.allowed_user_ids:
            await message.reply_text("This bot is restricted to approved users.")
            return
        await chat.send_action("typing")
        try:
            response = await self.api.ask(
                message.text,
                user_id=f"telegram:{user.id}",
                session_id=f"telegram-chat:{chat.id}",
            )
            for part in split_message(
                format_agentic_response(response), self.settings.max_message_characters
            ):
                await message.reply_text(part, disable_web_page_preview=True)
        except Exception:
            logger.exception("telegram.question_failed", extra={"user_id": user.id})
            await message.reply_text(
                "Paperforge could not answer right now. Please try again later."
            )

    async def _error(self, update: object, context: Any) -> None:
        error = context.error
        logger.error(
            "telegram.update_failed",
            exc_info=(type(error), error, error.__traceback__) if error is not None else False,
            extra={"update": str(update)},
        )

    async def _post_shutdown(self, application: Any) -> None:
        del application
        await self.api.close()
