"""Academic paper persistence model."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from paperforge.models.base import Base


class Paper(Base):
    """Stored arXiv metadata and parsed document content."""

    __tablename__ = "papers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    arxiv_id: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(JSONB)
    abstract: Mapped[str] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(JSONB)
    published_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pdf_url: Mapped[str] = mapped_column(Text)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sections: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    references: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    parser_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pdf_processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    pdf_processing_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
