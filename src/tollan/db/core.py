"""Connections, transactions and reflected tables for SQLAlchemy users.

Create a resource from a URL, then open a transaction for each operation::

    >>> from sqlalchemy import text
    >>> with SqlaDB.from_url("sqlite://") as db:
    ...     with db.session_context() as session:
    ...         value = session.scalar(text("select 42"))
    >>> value
    42

Pass an existing engine to ``SqlaDB(engine)`` to borrow it. Closing that resource
leaves the engine available to its owner. Connections and sessions opened through
the resource are scoped to their own with statements.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Self

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker

from .sqlite import _register_bitwise_aggregates

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from types import TracebackType
    from typing import Any

    from sqlalchemy import Connection, Engine
    from sqlalchemy.engine import URL
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.schema import Table

__all__ = ["SqlaDB"]


class SqlaDB:
    """SQLAlchemy connections and transactions using one engine.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        Borrowed engine. The caller retains responsibility for disposing it.
    metadata : sqlalchemy.MetaData or None, optional
        Table definitions to use. None creates empty metadata. Construction does
        not reflect tables, create a schema or open a connection.

    Attributes
    ----------
    engine : sqlalchemy.Engine
        Engine used for connections and sessions.
    metadata : sqlalchemy.MetaData
        Supplied or reflected table definitions.
    session_factory : sqlalchemy.orm.sessionmaker
        Factory for callers that need to manage a session themselves. Such
        sessions must be closed by the caller.

    Notes
    -----
    SQLite connections provide bit_and and bit_or aggregates for integer values.
    NULL values raise a query error rather than being skipped.
    """

    def __init__(self, engine: Engine, *, metadata: MetaData | None = None) -> None:
        self.engine = engine
        self.metadata = MetaData() if metadata is None else metadata
        self.session_factory = sessionmaker(bind=engine)
        self._owns_engine = False
        if engine.dialect.name == "sqlite":
            _register_bitwise_aggregates(engine)

    @classmethod
    def from_url(
        cls,
        url: str | URL,
        *,
        engine_options: Mapping[str, Any] | None = None,
        metadata: MetaData | None = None,
    ) -> Self:
        """Create a resource that owns its engine.

        Parameters
        ----------
        url : str or sqlalchemy.engine.URL
            SQLAlchemy database URL, including the selected driver.
        engine_options : mapping or None, optional
            Keyword options for sqlalchemy.create_engine, such as echo or
            connect_args. None uses that function's defaults.
        metadata : sqlalchemy.MetaData or None, optional
            Table definitions to use; None creates empty metadata.

        Returns
        -------
        Self
            Resource whose close method disposes the created engine. Use it in a
            with statement, or close it when the owning application shuts down.
        """
        resource = cls(create_engine(url, **(engine_options or {})), metadata=metadata)
        resource._owns_engine = True
        return resource

    @property
    def tables(self) -> Mapping[str, Table]:
        """Table definitions in this resource's metadata."""
        return self.metadata.tables

    def reflect_tables(self) -> None:
        """Read available table definitions into this resource's metadata."""
        self.metadata.reflect(bind=self.engine)

    def connect(self) -> Connection:
        """Open a connection for use in a with statement.

        Returns
        -------
        sqlalchemy.Connection
            Caller-scoped connection. Exiting its context closes it and rolls
            back any uncommitted transaction.
        """
        return self.engine.connect()

    @contextmanager
    def session_context(self) -> Iterator[Session]:
        """Open a fresh session and transaction for one operation.

        Yields
        ------
        sqlalchemy.orm.Session
            Fresh session. Successful exit commits pending work; exceptional exit
            rolls it back. Both paths close the session. Explicit commits within
            the context remain committed if later work fails.

        Notes
        -----
        Each call creates a session, including nested calls. Pass the yielded
        session to operations that must share a transaction. ORM objects are
        detached on exit; load required values before leaving the context.
        """
        with self.session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def close(self) -> None:
        """Dispose the engine created by from_url; leave a borrowed engine open."""
        if self._owns_engine:
            self.engine.dispose()

    def __enter__(self) -> Self:
        """Enter the resource's lifetime."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the owned engine on scope exit."""
        self.close()
