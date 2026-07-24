"""Tests for PostgreSQL adapter ownership semantics."""

from unittest.mock import MagicMock, patch

import pytest

from paperforge.core.config import DatabaseSettings
from paperforge.infrastructure.database import Database


def test_database_ping_session_and_close() -> None:
    engine = MagicMock()
    connection = MagicMock()
    connection.scalar.return_value = 1
    engine.connect.return_value.__enter__.return_value = connection
    session = MagicMock()

    with (
        patch("paperforge.infrastructure.database.create_engine", return_value=engine),
        patch("paperforge.infrastructure.database.sessionmaker", return_value=lambda: session),
    ):
        database = Database(DatabaseSettings())
        assert database.engine is engine
        assert database.ping() is True
        with database.session() as yielded:
            assert yielded is session
        database.close()

    session.commit.assert_called_once_with()
    session.close.assert_called_once_with()
    engine.dispose.assert_called_once_with()


def test_database_session_rolls_back_on_error() -> None:
    engine = MagicMock()
    session = MagicMock()

    with (
        patch("paperforge.infrastructure.database.create_engine", return_value=engine),
        patch("paperforge.infrastructure.database.sessionmaker", return_value=lambda: session),
    ):
        database = Database(DatabaseSettings())
        with pytest.raises(RuntimeError, match="boom"), database.session():
            raise RuntimeError("boom")

    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()
    session.commit.assert_not_called()
