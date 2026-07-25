"""Schemas for Week 6 observability and user feedback."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackRequest(BaseModel):
    """User score attached to one Langfuse trace."""

    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(min_length=32, max_length=32)
    value: Literal[0, 1]
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 32 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("trace_id must be a 32-character lowercase hexadecimal value")
        return normalized

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class FeedbackResponse(BaseModel):
    """Confirmation that a feedback score was queued."""

    model_config = ConfigDict(frozen=True)

    accepted: bool
    trace_id: str
    score_name: str
