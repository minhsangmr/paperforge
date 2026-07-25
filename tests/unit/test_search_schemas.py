"""Tests for public search request validation."""

from datetime import date

import pytest
from pydantic import ValidationError

from paperforge.schemas.search import SearchRequest


def test_offset_is_derived_from_page() -> None:
    request = SearchRequest(query="retrieval", page=4, page_size=25)
    assert request.offset == 75


def test_inverted_date_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="published_from"):
        SearchRequest(
            query="retrieval",
            published_from=date(2026, 7, 24),
            published_to=date(2026, 7, 1),
        )


def test_blank_query_is_rejected() -> None:
    with pytest.raises(ValidationError, match="blank"):
        SearchRequest(query="   ")
