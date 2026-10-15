# Database connections, models and transactions

Use `SqlaDB` to run SQLAlchemy queries, share an engine across operations, and
reflect an existing database's tables. Shared column and actor declarations
provide consistent identities, timestamps, and attribution in your own models.

| Task | API |
| --- | --- |
| Create and own an engine | `SqlaDB.from_url(url)` |
| Borrow an existing engine | `SqlaDB(engine, metadata=metadata)` |
| Open a connection | `db.connect()` |
| Run an ORM transaction | `db.session_context()` |
| Read existing table definitions | `db.reflect_tables()` |
| Release an owned engine | A resource `with` statement or `db.close()` |
| Define common columns | [Shared column conventions](#define-orm-columns-with-shared-conventions) |
| Record creation and modification actors | [Actor attribution](#record-who-created-and-modified-data) |
| Insert or update prepared rows | [Batch upsert](#insert-or-update-a-batch-in-sqlite) |

## Connections and transactions

### Run independent operations

Keep a resource for the lifetime of your script, app or worker. Each operation
opens its own connection or session. A successful session context commits pending
work; an exception rolls it back. Both exits close the session.

```{testcode}
from sqlalchemy import text
from tollan.db import SqlaDB

with SqlaDB.from_url("sqlite://") as db:
    with db.session_context() as session:
        session.execute(text("create table reading (value integer)"))
        session.execute(text("insert into reading values (42)"))

    with db.connect() as connection:
        value = connection.scalar(text("select value from reading"))

print(value)
```

```{testoutput}
42
```

A connection context closes the connection without committing pending writes.
Use a session context for automatic commit/rollback, or manage a transaction
through SQLAlchemy yourself. An explicit commit inside a session context remains
committed if a later operation in that context fails.

`engine_options` passes SQLAlchemy engine settings when creating a resource:

```python
with SqlaDB.from_url(url, engine_options={"echo": True}) as db:
    ...
```

Open sessions and connections must finish before their owning resource closes.
An application may keep the resource across requests; each request opens its own
session. `session_factory` is available when a caller needs to manage a session's
transaction and closing explicitly.

### Share a transaction across operations

Pass one session to operations whose pending work must commit or roll back
together. Each call to `session_context()` creates a different session, including
calls nested inside another session context.

```{testcode}
def record_reading(session, value):
    session.execute(
        text("insert into reading values (:value)"), {"value": value}
    )

def count_readings(session):
    return session.scalar(text("select count(*) from reading"))

with SqlaDB.from_url("sqlite://") as db:
    with db.session_context() as session:
        session.execute(text("create table reading (value integer)"))
        record_reading(session, 7)
        record_reading(session, 8)
        print(count_readings(session))
```

```{testoutput}
2
```

Closing a session detaches its ORM objects. Unloaded or expired attributes cannot
fetch values afterward; SQLAlchemy expires ORM attributes on commit by default.
Read the values needed by the caller inside the context and return those values,
or let the caller supply and manage the session for further ORM work.

### Borrow an engine and reflect tables

Wrap an engine supplied by another component without taking over its lifetime.
The wrapper's `close()` leaves that engine available to its owner. For example,
a Flask-SQLAlchemy application can pass its selected engine and metadata.

```{testcode}
from sqlalchemy import MetaData, create_engine, select

engine = create_engine("sqlite://")
try:
    with engine.begin() as connection:
        connection.execute(text("create table reading (value integer)"))
        connection.execute(text("insert into reading values (7)"))

    metadata = MetaData()
    with SqlaDB(engine, metadata=metadata) as db:
        db.reflect_tables()
        reading = db.tables["reading"]
        with db.session_context() as session:
            print(session.scalar(select(reading.c.value)))
finally:
    engine.dispose()
```

```{testoutput}
7
```

Construction does not connect or reflect tables. `reflect_tables()` explicitly
reads the database into the supplied metadata, or into the resource's initially
empty metadata. Schema creation remains an explicit application operation.

## Schema conventions

### Define ORM columns with shared conventions

Use `tollan.db.mapped_types` annotations inside SQLAlchemy's `Mapped[...]`:

| Annotation | Column convention |
| --- | --- |
| `Pk` | Integer primary key |
| `Uuid` | Python `uuid.UUID`, generated on SQLAlchemy INSERT when omitted |
| `Label` | Indexed descriptive label, length 128 |
| `Name` | Nullable display name, length 512 |
| `Desc` | Nullable text description |
| `Timestamp` | Application-supplied UTC timestamp |
| `Created_at` | Indexed UTC timestamp, defaulted on INSERT |
| `Updated_at` | Indexed UTC timestamp, defaulted on INSERT and SQLAlchemy UPDATE |
| `Timezone` | IANA timezone as `zoneinfo.ZoneInfo`, defaulted to the local timezone |

Use `TimestampMixin` for both creation and modification timestamps. Add uniqueness
when a label must be unique. Define context-specific string lengths and JSON
columns directly.

```{testcode}
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from tollan.db.mapped_types import Label, Name, Pk, Timestamp, TimestampMixin, Uuid, fk

class Base(DeclarativeBase):
    pass

class Device(TimestampMixin, Base):
    __tablename__ = "device"
    pk: Mapped[Pk]
    uid: Mapped[Uuid] = mapped_column(unique=True)
    label: Mapped[Label] = mapped_column(unique=True)
    name: Mapped[Name | None]

class Reading(Base):
    __tablename__ = "reading"
    pk: Mapped[Pk]
    device_fk: Mapped[int] = fk(Device)
    value: Mapped[float]
    observed_at: Mapped[Timestamp]

with SqlaDB.from_url("sqlite://", metadata=Base.metadata) as db:
    Base.metadata.create_all(db.engine)
    with db.session_context() as session:
        device = Device(label="sensor-a")
        session.add(device)
        session.flush()
        assert isinstance(device.uid, UUID)
        session.add(Reading(
            device_fk=device.pk, value=12.5,
            observed_at=datetime(2026, 10, 14, 12),
        ))
    with db.session_context() as session:
        print(session.execute(select(Device.label, Reading.value).join(Reading)).one())
```

```{testoutput}
('sensor-a', 12.5)
```

`Uuid` generates a UUID4 when a SQLAlchemy INSERT omits the value. It is
available after `session.flush()`. Supply a `uuid.UUID` explicitly to retain an
existing identity. Uniqueness is a separate column constraint. Direct SQL
INSERTs must supply the UUID themselves.

`fk(Device)` references the mapped `pk` column. `fk("device")` supports forward
references to the same table. No cascading action is declared by default;
`ondelete="CASCADE"` or `onupdate="CASCADE"` requests one explicitly.

Timestamps are stored as UTC without a timezone. Supply UTC values when assigning
them explicitly. `Timestamp` has no automatic value; use it for event times
supplied by the application. `Created_at` and `Updated_at` receive database defaults
on INSERT. `Updated_at` also updates on SQLAlchemy writes that omit it. Direct SQL UPDATEs
must assign it explicitly. `Timezone` describes a separate local context, such as
an actor's timezone; it does not change the timestamp convention.

### Set a database-generated timestamp

Use `utcnow()` as a column's `server_default` to fill in the timestamp when an
INSERT omits that column. An explicitly supplied timestamp is preserved.

```{testcode}
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, Table
from tollan.db.func import utcnow

metadata = MetaData()
reading = Table(
    "reading", metadata,
    Column("pk", Integer, primary_key=True),
    Column("created_at", DateTime, server_default=utcnow()),
)
with SqlaDB.from_url("sqlite://", metadata=metadata) as db:
    metadata.create_all(db.engine)
    with db.session_context() as session:
        session.execute(reading.insert().values(pk=1))
        timestamp = session.scalar(select(reading.c.created_at))

print(isinstance(timestamp, datetime))
```

```{testoutput}
True
```

The expression uses the database clock. Timestamp precision and timezone
information on returned datetimes depend on the database and column type.
An INSERT default does not update the timestamp when the row changes.

## Record who created and modified data

Define an `Actor` in your application's declarative registry. Its portable `uid`
is a Python `uuid.UUID`, generated on insertion when omitted. It
identifies the actor across databases; `pk` is local to the database. `name` is a
readable display name. Put stable environment facts in `meta`; keep invocation
commands, configurations and inputs with the run that used them.

```{testcode}
from tollan.db.orm import ActorBase, AuditMixin

class Actor(ActorBase, Base):
    pass

class Calibration(AuditMixin, Base):
    __tablename__ = "calibration"
    pk: Mapped[Pk]
    value: Mapped[float]

with SqlaDB.from_url("sqlite://", metadata=Base.metadata) as db:
    Base.metadata.create_all(db.engine)
    with db.session_context() as session:
        actor = Actor(
            uid=UUID("a43ed253-389f-4e17-880d-31e441301ae4"),
            name="site reduction",
            meta={"hostname": "site", "timezone": "America/Mexico_City"},
        )
        calibration = Calibration(
            value=1.5, created_by=actor, updated_by=actor
        )
        session.add(calibration)
    with db.session_context() as session:
        calibration = session.scalar(select(Calibration))
        print(calibration.created_by.name, calibration.value)
```

```{testoutput}
site reduction 1.5
```

`ActorMixin` supplies only the actor references. `AuditMixin` includes timestamps
too. Unknown attribution remains null. Your write workflow selects actors and
sets attribution; the mixins do not open sessions or identify the current actor.

## Batch writes and query helpers

### Insert or update a batch in SQLite

Use `batch_upsert` for prepared rows, matching an existing unique constraint.
It keeps the existing row's primary key when the batch omits that key. The caller
owns the transaction; an error in that transaction rolls back the batch too.

```{testcode}
from tollan.db.orm import batch_upsert

with SqlaDB.from_url("sqlite://", metadata=Base.metadata) as db:
    Base.metadata.create_all(db.engine)
    with db.session_context() as session:
        batch_upsert(
            session, Device, [{"label": "sensor-a", "name": "Initial"}],
            index_elements=[Device.label],
        )
        batch_upsert(
            session, Device, [{"label": "sensor-a", "name": "Updated"}],
            index_elements=[Device.label],
        )
    with db.session_context() as session:
        print(session.scalar(select(Device.name)))
```

```{testoutput}
Updated
```

Each batch contains the same column keys in every row. Supplied columns other
than the conflict keys are updated. An omitted `updated_at` uses its column
default; a supplied value is preserved. This bulk SQL operation does not execute
per-object flush hooks or relationship operations. Prepare any application
validation and actor attribution before calling it.

### SQLite query functions

SQLite connections opened through `SqlaDB` provide `bit_and` and `bit_or` for
integer columns. NULL values raise a query error; filter or replace them explicitly
when the query requires that behavior. This also applies when borrowing an
already-used engine.

`create_datetime(date_column, time_column)` combines SQL date and time columns for
SQLite and MySQL queries.

See the {ref}`database API reference <database-resources>`.
