"""OpenSearch connectivity and index bootstrap."""

from typing import Any, cast
from urllib.parse import urlparse

from opensearchpy import OpenSearch

from paperforge.core.config import OpenSearchSettings

BASE_PAPER_INDEX: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "dynamic": True,
        "properties": {
            "id": {"type": "keyword"},
            "arxiv_id": {"type": "keyword"},
            "title": {"type": "text"},
            "abstract": {"type": "text"},
            "authors": {"type": "keyword"},
            "categories": {"type": "keyword"},
            "published_date": {"type": "date"},
        },
    },
}


class OpenSearchClient:
    """Small adapter around opensearch-py."""

    def __init__(self, settings: OpenSearchSettings, client: Any | None = None) -> None:
        self.settings = settings
        self._client: Any = client or self._build_client(settings)

    @staticmethod
    def _build_client(settings: OpenSearchSettings) -> Any:
        parsed = urlparse(settings.url)
        if parsed.hostname is None:
            raise ValueError("OpenSearch URL must include a hostname")

        auth = None
        if parsed.username is not None:
            auth = (parsed.username, parsed.password or "")

        return OpenSearch(
            hosts=[
                {
                    "host": parsed.hostname,
                    "port": parsed.port or (443 if parsed.scheme == "https" else 9200),
                    "scheme": parsed.scheme or "http",
                }
            ],
            http_auth=auth,
            use_ssl=parsed.scheme == "https",
            verify_certs=parsed.scheme == "https",
            timeout=settings.timeout_seconds,
        )

    def ping(self) -> bool:
        """Return true when the cluster is reachable and not red."""

        health = cast(dict[str, Any], self._client.cluster.health())
        return health.get("status") in {"green", "yellow"}

    def ensure_index(self) -> bool:
        """Create the base paper index once; return true when created."""

        if bool(self._client.indices.exists(index=self.settings.index_name)):
            return False
        self._client.indices.create(index=self.settings.index_name, body=BASE_PAPER_INDEX)
        return True

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._client.close()
