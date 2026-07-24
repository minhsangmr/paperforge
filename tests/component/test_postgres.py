"""PostgreSQL component tests against Docker Compose."""

import pytest
from sqlalchemy import inspect, text

from paperforge.core.config import get_settings
from paperforge.infrastructure.database import Database

pytestmark = pytest.mark.component


def test_alembic_created_papers_table_and_database_is_queryable() -> None:
    database = Database(get_settings().database)
    try:
        assert database.ping() is True
        assert "papers" in inspect(database.engine).get_table_names()
        with database.session() as session:
            assert session.scalar(text("SELECT 1")) == 1
    finally:
        database.close()
