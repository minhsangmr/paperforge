"""Create the papers table.

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create application persistence tables."""

    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("arxiv_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pdf_url", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parser_used", sa.String(length=64), nullable=True),
        sa.Column("parser_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pdf_processed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("pdf_processing_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_papers")),
        sa.UniqueConstraint("arxiv_id", name=op.f("uq_papers_arxiv_id")),
    )
    op.create_index(op.f("ix_papers_published_date"), "papers", ["published_date"], unique=False)


def downgrade() -> None:
    """Drop application persistence tables."""

    op.drop_index(op.f("ix_papers_published_date"), table_name="papers")
    op.drop_table("papers")
