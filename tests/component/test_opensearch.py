"""OpenSearch component tests against Docker Compose."""

import pytest

from paperforge.core.config import get_settings
from paperforge.infrastructure.opensearch import OpenSearchClient

pytestmark = pytest.mark.component


def test_index_bootstrap_is_idempotent() -> None:
    client = OpenSearchClient(get_settings().opensearch)
    try:
        assert client.ping() is True
        client.ensure_index()
        assert client.ensure_index() is False
    finally:
        client.close()
