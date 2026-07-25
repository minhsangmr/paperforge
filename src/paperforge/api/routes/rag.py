"""Week 5 complete and streaming RAG endpoints."""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from paperforge.api.dependencies import RAGServiceDep
from paperforge.exceptions import EmbeddingUnavailableError, OllamaError
from paperforge.schemas.rag import RAGRequest, RAGResponse, RAGStreamEvent
from paperforge.services.rag import encode_sse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rag"])


@router.post("/ask", response_model=RAGResponse)
async def ask_question(request: RAGRequest, service: RAGServiceDep) -> RAGResponse:
    """Retrieve relevant chunks and return a complete Ollama answer."""

    try:
        return await service.answer(request)
    except EmbeddingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("rag.request_failed", extra={"query": request.query})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is temporarily unavailable",
        ) from exc


@router.post("/stream")
async def stream_answer(request: RAGRequest, service: RAGServiceDep) -> StreamingResponse:
    """Stream a grounded answer using standards-compliant Server-Sent Events."""

    async def events() -> AsyncIterator[str]:
        try:
            async for event in service.stream(request):
                yield encode_sse(event)
        except (EmbeddingUnavailableError, OllamaError, ValueError) as exc:
            yield encode_sse(RAGStreamEvent(event="error", data={"detail": str(exc)}))
        except Exception:
            logger.exception("rag.stream_failed", extra={"query": request.query})
            yield encode_sse(
                RAGStreamEvent(
                    event="error",
                    data={"detail": "RAG stream is temporarily unavailable"},
                )
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
