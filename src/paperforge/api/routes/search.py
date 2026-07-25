"""BM25 paper-search endpoints."""

import logging
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from paperforge.api.dependencies import SearchServiceDep
from paperforge.schemas.search import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


async def _execute(service: SearchServiceDep, request: SearchRequest) -> SearchResponse:
    try:
        return await service.search(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("search.request_failed", extra={"query": request.query})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search service is temporarily unavailable",
        ) from exc


@router.get("", response_model=SearchResponse)
async def search_get(
    service: SearchServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=500, pattern=r".*\S.*")],
    category: Annotated[list[str] | None, Query()] = None,
    published_from: date | None = None,
    published_to: date | None = None,
    processed_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 10,
    sort: Literal["relevance", "published_desc", "published_asc"] = "relevance",
) -> SearchResponse:
    """Run a bookmarkable BM25 query using URL parameters."""

    request = SearchRequest(
        query=q,
        categories=category or [],
        published_from=published_from,
        published_to=published_to,
        processed_only=processed_only,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return await _execute(service, request)


@router.post("", response_model=SearchResponse)
async def search_post(
    request: SearchRequest,
    service: SearchServiceDep,
) -> SearchResponse:
    """Run an advanced BM25 query from a JSON request body."""

    return await _execute(service, request)
