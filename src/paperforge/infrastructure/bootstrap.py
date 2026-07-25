"""Idempotent OpenSearch bootstrap command."""

import json

from paperforge.core.config import get_settings
from paperforge.infrastructure.opensearch import OpenSearchClient


def main() -> None:
    """Create the versioned BM25 index when search is enabled."""

    settings = get_settings()
    if not settings.opensearch.enabled:
        print(json.dumps({"opensearch": "disabled"}))
        return

    client = OpenSearchClient(settings.opensearch)
    try:
        created = client.ensure_index()
        schema_version = client.index_schema_version()
    finally:
        client.close()

    print(
        json.dumps(
            {
                "opensearch": "created" if created else "already_exists",
                "index": settings.opensearch.index_name,
                "schema_version": schema_version,
            }
        )
    )


if __name__ == "__main__":
    main()
