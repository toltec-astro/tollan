"""Shared resources preserve transaction isolation and engine ownership."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    create_engine,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tollan.db import SqlaDB
from tollan.db.func import create_datetime, utcnow


def test_transactions_commit_rollback_and_close():
    with SqlaDB.from_url("sqlite://") as db:
        with db.session_context() as first:
            first.execute(text("create table reading (value integer)"))
            first.execute(text("insert into reading values (1)"))
        with (  # noqa: PT012 -- exercise rollback for an error inside a transaction.
            pytest.raises(RuntimeError, match="cancel"),
            db.session_context() as failed,
        ):
            failed.execute(text("insert into reading values (2)"))
            message = "cancel"
            raise RuntimeError(message)
        with db.session_context() as last:
            assert last.scalars(text("select value from reading")).all() == [1]
        assert first is not failed and failed is not last
        assert not first.in_transaction()
        assert not failed.in_transaction()
        assert not last.in_transaction()


def test_explicit_commit_can_be_followed_by_more_work():
    with SqlaDB.from_url("sqlite://") as db:
        with db.session_context() as session:
            session.execute(text("create table reading (value integer)"))
            session.execute(text("insert into reading values (1)"))
            session.commit()
            session.execute(text("insert into reading values (2)"))
        with db.session_context() as session:
            assert session.scalars(
                text("select value from reading order by value")
            ).all() == [1, 2]


def test_nested_contexts_have_distinct_sessions_and_detach_objects():
    class Base(DeclarativeBase):
        pass

    class Reading(Base):
        __tablename__ = "reading"
        value: Mapped[int] = mapped_column(primary_key=True)

    with SqlaDB.from_url("sqlite://") as db:
        Base.metadata.create_all(db.engine)
        with db.session_context() as outer:
            reading = Reading(value=1)
            outer.add(reading)
            with db.session_context() as inner:
                assert inner is not outer
            assert inspect(reading).session is outer
        assert inspect(reading).detached


def test_same_models_can_query_two_databases_independently():
    class Base(DeclarativeBase):
        pass

    class Reading(Base):
        __tablename__ = "reading"
        value: Mapped[int] = mapped_column(primary_key=True)

    with SqlaDB.from_url("sqlite://") as source, SqlaDB.from_url("sqlite://") as target:
        for db, value in ((source, 1), (target, 2)):
            Base.metadata.create_all(db.engine)
            with db.session_context() as session:
                session.add(Reading(value=value))
        with source.session_context() as source_session:
            with target.session_context() as target_session:
                assert source_session.scalar(select(Reading.value)) == 1
                assert target_session.scalar(select(Reading.value)) == 2
            assert source_session.scalar(select(Reading.value)) == 1


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        (sqlite.dialect(), "CURRENT_TIMESTAMP"),
        (mysql.dialect(), "UTC_TIMESTAMP()"),
        (postgresql.dialect(), "TIMEZONE('utc', CURRENT_TIMESTAMP)"),
    ],
)
def test_utcnow_preserves_dialect_expressions(dialect, expected):
    assert str(utcnow().compile(dialect=dialect)) == expected


def test_utcnow_default_populates_omitted_timestamp_and_preserves_explicit_value():
    metadata = MetaData()
    reading = Table(
        "reading",
        metadata,
        Column("pk", Integer, primary_key=True),
        Column("created_at", DateTime, server_default=utcnow()),
    )
    explicit = datetime(2000, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    before = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    with SqlaDB.from_url("sqlite://", metadata=metadata) as db:
        metadata.create_all(db.engine)
        with db.session_context() as session:
            session.execute(reading.insert().values(pk=1))
            session.execute(reading.insert().values(pk=2, created_at=explicit))
            timestamps = session.scalars(
                select(reading.c.created_at).order_by(reading.c.pk)
            ).all()
    after = datetime.now(UTC).replace(tzinfo=None)
    assert before <= timestamps[0] <= after
    assert timestamps[1] == explicit


def test_owned_and_borrowed_engine_lifetimes():
    disposed = []
    with SqlaDB.from_url("sqlite://") as owner:
        event.listen(owner.engine, "engine_disposed", disposed.append)
        with owner.session_context() as session:
            session.execute(text("create table reading (value integer)"))
        with SqlaDB(owner.engine) as borrower, borrower.connect() as connection:
            connection.execute(text("insert into reading values (3)"))
        assert not disposed
        with owner.connect() as connection:
            # A connection scope does not commit writes.
            assert connection.scalar(text("select count(*) from reading")) == 0
    assert disposed == [owner.engine]


def test_borrowed_metadata_and_explicit_reflection():
    engine = create_engine("sqlite://")
    connected = []
    event.listen(engine, "connect", lambda *_: connected.append(True))
    metadata = MetaData()
    try:
        with SqlaDB(engine, metadata=metadata) as db:
            assert db.metadata is metadata
            assert not connected
            assert not db.tables
            with engine.begin() as connection:
                connection.execute(text("create table reading (value integer)"))
                connection.execute(text("create table extra (value integer)"))
            db.reflect_tables()
            assert set(db.tables) == {"reading", "extra"}
            with db.session_context() as session:
                assert session.scalars(select(db.tables["reading"])).all() == []
    finally:
        engine.dispose()


def test_sqlite_portable_query_functions_on_existing_pool():
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("select 1")) == 1
        with SqlaDB(engine) as db, SqlaDB(engine), db.connect() as connection:
            result = connection.execute(
                text(
                    "select bit_and(value), bit_or(value) from "
                    "(select 3 as value union all select 6)"
                )
            ).one()
            assert result == (2, 7)
            timestamp = connection.scalar(
                select(create_datetime(text("'2025-10-31'"), text("'09:26:59'")))
            )
            assert isinstance(timestamp, datetime)
            assert timestamp.isoformat() == "2025-10-31T09:26:59"
    finally:
        engine.dispose()
    statement = select(create_datetime(text("date_column"), text("time_column")))
    assert "TIMESTAMP(date_column, time_column)" in str(
        statement.compile(dialect=mysql.dialect())
    )


@pytest.mark.parametrize("function", ["bit_and", "bit_or"])
@pytest.mark.parametrize(
    "values", ["select null as value", "select 3 as value union all select null"]
)
def test_sqlite_bitwise_null_is_not_silently_skipped(function, values):
    with SqlaDB.from_url("sqlite://") as db, db.connect() as connection:
        # SQL fragments are fixed parameters in this test, not caller input.
        statement = text(f"select {function}(value) from ({values})")  # noqa: S608
        with pytest.raises(OperationalError):
            connection.scalar(statement)


@pytest.mark.parametrize(
    ("dialect", "n_args"),
    [
        (sqlite.dialect(), 0),
        (sqlite.dialect(), 1),
        (sqlite.dialect(), 3),
        (mysql.dialect(), 3),
    ],
)
def test_create_datetime_rejects_invalid_argument_counts(dialect, n_args):
    expression = create_datetime(*(text("argument") for _ in range(n_args)))
    with pytest.raises(TypeError, match="only supports two arguments"):
        expression.compile(dialect=dialect)
