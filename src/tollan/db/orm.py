"""Actor attribution and bulk operations for application-owned ORM models.

Define an ``Actor`` in your application's declarative registry with ``ActorBase``.
Use ``ActorMixin`` for creator/modifier references or ``AuditMixin`` to include
UTC timestamps too. Supply actors when writing records; these mixins do not select
an actor or open a session.

Examples
--------
>>> from sqlalchemy.orm import DeclarativeBase, Mapped
>>> from tollan.db.mapped_types import Pk
>>> class Base(DeclarativeBase):
...     pass
>>> class Actor(ActorBase, Base):
...     pass
>>> class Product(AuditMixin, Base):
...     __tablename__ = "product"
...     pk: Mapped[Pk]
>>> sorted(Product.__table__.c.keys())
['created_at', 'created_by_fk', 'pk', 'updated_at', 'updated_by_fk']
"""

from collections.abc import Mapping, Sequence  # noqa: TC003 -- runtime signatures
from typing import Any, cast

from sqlalchemy import JSON, ColumnDefault, Table
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import (
    Mapped,
    Session,
    class_mapper,
    declared_attr,
    mapped_column,
    relationship,
)

from .mapped_types import Created_at, Name, Pk, TimestampMixin, Uuid, fk

__all__ = ["ActorBase", "ActorMixin", "AuditMixin", "batch_upsert"]


class ActorBase:
    """Portable actor identity and stable environment facts.

    Combine with an application's declarative base to define its ``Actor`` model.
    Supply a readable ``name`` and stable facts in ``meta``. ``uid`` is a Python
    UUID, generated on insertion when omitted. Supply the existing UUID when
    importing an actor. Facts may include hostname, username, IANA timezone,
    deployment and software environment. Invocation-specific information belongs
    to the run record. The application owns identity reuse and immutability.
    """

    __tablename__ = "actor"
    pk: Mapped[Pk]
    uid: Mapped[Uuid] = mapped_column(unique=True)
    name: Mapped[Name] = mapped_column(nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="Stable actor facts"
    )
    created_at: Mapped[Created_at]


class ActorMixin:
    """Creation and modification actors; null means unknown attribution.

    Define an ``Actor`` model with table ``actor`` and primary key ``pk`` in the
    same declarative registry. Assign ``created_by`` and ``updated_by`` explicitly
    or through the application's write workflow.
    """

    created_by_fk: Mapped[int | None] = fk("actor", nullable=True)
    updated_by_fk: Mapped[int | None] = fk("actor", nullable=True)

    @declared_attr
    @classmethod
    def created_by(cls) -> Mapped[ActorBase | None]:
        """Actor that created the record."""
        return relationship("Actor", foreign_keys=[cls.created_by_fk])

    @declared_attr
    @classmethod
    def updated_by(cls) -> Mapped[ActorBase | None]:
        """Actor that last modified the record."""
        return relationship("Actor", foreign_keys=[cls.updated_by_fk])


class AuditMixin(TimestampMixin, ActorMixin):
    """Creation and modification timestamps with actor attribution."""


def batch_upsert(
    session: Session,
    model: type,
    data: Sequence[Mapping[str, Any]],
    *,
    index_elements: Sequence[Any],
) -> Any:
    """Insert or update a batch of rows in SQLite within a supplied transaction.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Caller-owned session. This function neither commits nor closes it.
    model : type
        Table-mapped class receiving the rows.
    data : sequence of mappings
        Nonempty batch of column values with the same keys in each row. Columns
        other than the conflict keys are updated from the supplied values. When
        omitted, a conventional ``Updated_at`` column uses its SQL INSERT
        default expression.
    index_elements : sequence
        Columns identifying the unique constraint used to match existing rows.
        Accepts column names or mapped columns.

    Returns
    -------
    sqlalchemy.engine.Result
        Execution result of the INSERT statement.

    Raises
    ------
    ValueError
        The batch is empty or its rows have different keys.
    NotImplementedError
        The session is bound to a backend other than SQLite.

    Notes
    -----
    This bulk SQL operation does not run per-object flush hooks or relationship
    operations. Prepare application validation and actor attribution before the
    call. An explicitly supplied ``updated_at`` is retained.
    """
    if not data:
        msg = "data cannot be empty"
        raise ValueError(msg)
    keys = set(data[0])
    if any(set(row) != keys for row in data):
        msg = "batch rows must have the same column keys"
        raise ValueError(msg)
    if session.get_bind(mapper=model).dialect.name != "sqlite":
        msg = "batch_upsert supports SQLite"
        raise NotImplementedError(msg)
    table = cast("Table", class_mapper(model, configure=False).local_table)
    statement = insert(table).values(list(data))
    conflict_keys = {key if isinstance(key, str) else key.key for key in index_elements}
    values = {key: statement.excluded[key] for key in keys - conflict_keys}
    if "updated_at" in table.c and "updated_at" not in values:
        values["updated_at"] = cast("ColumnDefault", table.c.updated_at.default).arg
    if values:
        statement = statement.on_conflict_do_update(
            index_elements=index_elements, set_=values
        )
    else:
        statement = statement.on_conflict_do_nothing(index_elements=index_elements)
    return session.execute(statement)
