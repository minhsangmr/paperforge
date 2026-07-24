"""Tests for dependency factories and transactional sessions."""

from typing import cast
from unittest.mock import MagicMock

from paperforge.api.dependencies import get_database, get_db_session, get_health_service
from paperforge.core.config import Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.resources import Infrastructure


def test_database_and_session_dependencies() -> None:
    database = MagicMock()
    session = MagicMock()
    database.session.return_value.__enter__.return_value = session
    infrastructure = Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
    )

    assert get_database(infrastructure) is database
    generator = get_db_session(cast(Database, database))
    assert next(generator) is session
    try:
        next(generator)
    except StopIteration:
        pass
    else:
        raise AssertionError("session dependency must yield exactly once")


def test_health_service_factory_uses_infrastructure() -> None:
    database = MagicMock()
    infrastructure = Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
    )

    service = get_health_service(Settings(), infrastructure)

    assert service is not None
