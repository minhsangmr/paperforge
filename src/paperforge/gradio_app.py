"""Containerized Gradio client for the observable, cached RAG API."""

import json
from collections.abc import AsyncIterator

import gradio as gr
import httpx

from paperforge.core.config import get_settings


def _format_answer(answer: str, metadata: dict[str, object]) -> str:
    output = answer
    sources = metadata.get("sources")
    if isinstance(sources, list) and sources:
        output += "\n\n### Sources\n"
        for item in sources:
            if isinstance(item, dict):
                citation = str(item.get("citation", ""))
                title = str(item.get("title", "Untitled"))
                url = str(item.get("pdf_url", ""))
                output += f"- [{citation}] [{title}]({url})\n"
    mode = metadata.get("search_mode")
    chunks = metadata.get("chunks_used")
    cache = "hit" if metadata.get("cache_hit") else "miss"
    trace_id = metadata.get("trace_id") or "disabled"
    output += f"\n_Search: {mode}; chunks: {chunks}; cache: {cache}; trace: `{trace_id}`_"
    return output


async def stream_answer(
    query: str,
    top_k: int,
    use_hybrid: bool,
    model: str,
    categories: str,
) -> AsyncIterator[tuple[str, str]]:
    """Proxy SSE and expose the trace id for user feedback."""

    if not query.strip():
        yield "Please enter a question.", ""
        return
    settings = get_settings()
    payload = {
        "query": query,
        "top_k": int(top_k),
        "use_hybrid": use_hybrid,
        "model": model or None,
        "categories": [item.strip() for item in categories.split(",") if item.strip()],
    }
    answer = ""
    metadata: dict[str, object] = {}
    try:
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "POST", f"{settings.ui.api_base_url.rstrip('/')}/stream", json=payload
            ) as response,
        ):
            response.raise_for_status()
            event_name = "message"
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event_name = line.removeprefix("event: ").strip()
                elif line.startswith("data: "):
                    data = json.loads(line.removeprefix("data: "))
                    if event_name == "metadata" and isinstance(data, dict):
                        metadata = data
                    elif event_name == "token" and isinstance(data, dict):
                        answer += str(data.get("text", ""))
                        yield _format_answer(answer, metadata), str(metadata.get("trace_id") or "")
                    elif event_name == "done" and isinstance(data, dict):
                        answer = str(data.get("answer", answer))
                        yield _format_answer(answer, metadata), str(metadata.get("trace_id") or "")
                    elif event_name == "error" and isinstance(data, dict):
                        yield f"RAG error: {data.get('detail', 'unknown error')}", ""
    except httpx.HTTPError as exc:
        yield f"Could not reach the Paperforge API: {exc}", ""


async def submit_feedback(trace_id: str, value: int) -> str:
    """Attach a binary score to the most recent Langfuse trace."""

    if not trace_id:
        return "No trace is available. Enable and configure Langfuse first."
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.ui.api_base_url.rstrip('/')}/feedback",
                json={"trace_id": trace_id, "value": value},
            )
        response.raise_for_status()
        return "Feedback recorded."
    except httpx.HTTPError as exc:
        return f"Feedback failed: {exc}"


async def submit_positive_feedback(trace_id: str) -> str:
    return await submit_feedback(trace_id, 1)


async def submit_negative_feedback(trace_id: str) -> str:
    return await submit_feedback(trace_id, 0)


def create_interface() -> gr.Blocks:
    settings = get_settings()
    with gr.Blocks(title="Paperforge RAG") as interface:
        gr.Markdown("# Paperforge\nAsk grounded questions about indexed arXiv papers.")
        trace_id = gr.State("")
        query = gr.Textbox(label="Question", lines=2)
        with gr.Accordion("Retrieval and generation options", open=False):
            top_k = gr.Slider(1, settings.rag.max_top_k, value=settings.rag.default_top_k, step=1)
            use_hybrid = gr.Checkbox(value=True, label="Use hybrid retrieval")
            model = gr.Textbox(value=settings.rag.default_model, label="Ollama model")
            categories = gr.Textbox(label="arXiv categories", placeholder="cs.AI, cs.IR")
        submit = gr.Button("Ask", variant="primary")
        answer = gr.Markdown()
        with gr.Row():
            helpful = gr.Button("Helpful")
            unhelpful = gr.Button("Not helpful")
        feedback_status = gr.Markdown()
        inputs = [query, top_k, use_hybrid, model, categories]
        submit.click(stream_answer, inputs=inputs, outputs=[answer, trace_id])
        query.submit(stream_answer, inputs=inputs, outputs=[answer, trace_id])
        helpful.click(submit_positive_feedback, inputs=trace_id, outputs=feedback_status)
        unhelpful.click(submit_negative_feedback, inputs=trace_id, outputs=feedback_status)
    return interface


def main() -> None:
    settings = get_settings()
    create_interface().launch(
        server_name=settings.ui.host,
        server_port=settings.ui.port,
        share=False,
        show_error=True,
    )


if __name__ == "__main__":
    main()
