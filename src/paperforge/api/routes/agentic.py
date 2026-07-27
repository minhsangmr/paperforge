"""Week 7 bounded Agentic RAG endpoint."""

import logging

from fastapi import APIRouter, HTTPException, status

from paperforge.api.dependencies import AgenticRAGServiceDep
from paperforge.exceptions import EmbeddingUnavailableError, OllamaError
from paperforge.schemas.agentic import AgenticRAGRequest, AgenticRAGResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agentic-rag"])


@router.post("/agentic-ask", response_model=AgenticRAGResponse)
@router.post("/ask-agentic", response_model=AgenticRAGResponse, include_in_schema=False)
async def ask_agentic(
    request: AgenticRAGRequest,
    service: AgenticRAGServiceDep,
) -> AgenticRAGResponse:
    """Run guardrail, retrieval, grading, bounded rewriting, and grounded generation."""

    try:
        return await service.answer(request)
    except (EmbeddingUnavailableError, OllamaError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("agentic.request_failed", extra={"query": request.query})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agentic RAG service is temporarily unavailable",
        ) from exc
