"""PostgreSQL engine and session management."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from paperforge.core.config import DatabaseSettings


class Database:
    """Own the SQLAlchemy engine and transactional sessions."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self._engine: Engine = create_engine(
            settings.url,
            echo=settings.echo,
            pool_pre_ping=True,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout_seconds,
            connect_args={"connect_timeout": settings.connect_timeout_seconds},
        )
        self._session_factory = sessionmaker(
            bind=self._engine,
            class_=Session,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> Engine:
        """Expose the Engine for migrations and low-level diagnostics."""

        return self._engine

    def ping(self) -> bool:
        """Verify that a database connection can execute a trivial query."""

        with self._engine.connect() as connection:
            result: object = connection.scalar(text("SELECT 1"))
            return result == 1

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session with rollback-on-error semantics."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        """Dispose all pooled connections."""

        self._engine.dispose()
