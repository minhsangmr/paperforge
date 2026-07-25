"""Unified Week 4 BM25, vector, and RRF hybrid-search endpoint."""

import logging

from fastapi import APIRouter, HTTPException, status

from paperforge.api.dependencies import HybridSearchServiceDep
from paperforge.exceptions import EmbeddingUnavailableError
from paperforge.schemas.hybrid_search import HybridSearchRequest, HybridSearchResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hybrid-search", tags=["hybrid-search"])


@router.post("", response_model=HybridSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    service: HybridSearchServiceDep,
) -> HybridSearchResponse:
    """Search chunk documents using auto, BM25, vector, or RRF hybrid mode."""

    try:
        return await service.search(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except EmbeddingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("hybrid_search.request_failed", extra={"query": request.query})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="hybrid search is temporarily unavailable",
        ) from exc
