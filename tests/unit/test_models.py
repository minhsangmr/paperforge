"""Tests for SQLAlchemy model metadata."""

from paperforge.models.base import Base
from paperforge.models.paper import Paper


def test_paper_model_is_registered_with_expected_constraints() -> None:
    table = Base.metadata.tables["papers"]

    assert Paper.__tablename__ == "papers"
    assert table.c.arxiv_id.unique is True
    assert table.c.pdf_processed.default is not None
    assert table.c.published_date.index is True
