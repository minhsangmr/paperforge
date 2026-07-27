"""Executable entry point for the dedicated Telegram polling container."""

from paperforge.core.config import get_settings
from paperforge.core.logging import configure_logging
from paperforge.services.telegram.bot import TelegramBot
from paperforge.services.telegram.client import PaperforgeAPIClient


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    TelegramBot(settings.telegram, PaperforgeAPIClient(settings.telegram)).run()


if __name__ == "__main__":
    main()
