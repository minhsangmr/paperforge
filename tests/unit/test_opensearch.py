"""Tests for OpenSearch bootstrap behavior."""

from unittest.mock import MagicMock, patch

import pytest

from paperforge.core.config import OpenSearchSettings
from paperforge.infrastructure.opensearch import BASE_PAPER_INDEX, OpenSearchClient


def test_opensearch_bootstrap_is_idempotent() -> None:
    raw_client = MagicMock()
    raw_client.indices.exists.side_effect = [False, True]
    raw_client.cluster.health.return_value = {"status": "yellow"}
    adapter = OpenSearchClient(OpenSearchSettings(), client=raw_client)

    assert adapter.ping() is True
    assert adapter.ensure_index() is True
    assert adapter.ensure_index() is False
    adapter.close()

    raw_client.indices.create.assert_called_once_with(
        index="paperforge-papers-v1", body=BASE_PAPER_INDEX
    )
    raw_client.close.assert_called_once_with()


def test_opensearch_client_parses_url() -> None:
    with patch("paperforge.infrastructure.opensearch.OpenSearch") as constructor:
        OpenSearchClient(OpenSearchSettings(url="https://user:secret@search.example:9443"))

    constructor.assert_called_once()
    kwargs = constructor.call_args.kwargs
    assert kwargs["hosts"] == [{"host": "search.example", "port": 9443, "scheme": "https"}]
    assert kwargs["http_auth"] == ("user", "secret")
    assert kwargs["verify_certs"] is True


def test_opensearch_url_requires_hostname() -> None:
    with pytest.raises(ValueError, match="hostname"):
        OpenSearchClient(OpenSearchSettings(url="http:///missing-host"))
