"""Week 6 Langfuse feedback endpoint."""

from fastapi import APIRouter, HTTPException, status

from paperforge.api.dependencies import ObservabilityDep, SettingsDep
from paperforge.schemas.observability import FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["observability"])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    observability: ObservabilityDep,
    settings: SettingsDep,
) -> FeedbackResponse:
    if not observability.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Langfuse feedback is disabled or not configured",
        )
    accepted = await observability.submit_feedback(request)
    if not accepted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="feedback could not be queued",
        )
    return FeedbackResponse(
        accepted=True,
        trace_id=request.trace_id,
        score_name=settings.langfuse.score_name,
    )
