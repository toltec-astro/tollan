"""Conventional columns for SQLAlchemy declarative models.

Use these annotations inside ``Mapped[...]``. ``Pk`` declares an integer primary
key; ``Label``, ``Name`` and ``Desc`` describe human-readable fields. Add
``mapped_column(unique=True)`` when a label must be unique.

Timestamps contain UTC values without a stored timezone. Supply UTC datetimes
when assigning them explicitly. ``Timezone`` stores a separate IANA timezone,
such as an actor's local timezone.

Examples
--------
>>> from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
>>> class Base(DeclarativeBase):
...     pass
>>> class Device(TimestampMixin, Base):
...     __tablename__ = "device"
...     pk: Mapped[Pk]
...     label: Mapped[Label] = mapped_column(unique=True)
>>> Device.__table__.c.pk.primary_key
True
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, MappedColumn, class_mapper, mapped_column
from sqlalchemy_utils import TimezoneType
from tzlocal import get_localzone_name

from .func import utcnow

__all__ = [
    "Created_at",
    "Desc",
    "Label",
    "Name",
    "Pk",
    "Timestamp",
    "TimestampMixin",
    "Timezone",
    "Updated_at",
    "Uuid",
    "fk",
]

#: Integer primary key.
Pk = Annotated[
    int, mapped_column(Integer, primary_key=True, comment="Integer primary key")
]

#: UUID value, generated with uuid4 on SQLAlchemy INSERT when omitted.
Uuid = Annotated[UUID, mapped_column(UuidType(), default=uuid4, comment="UUID")]

#: Indexed descriptive label of up to 128 characters.
Label = Annotated[str, mapped_column(String(128), index=True, comment="Label")]

#: Nullable display name of up to 512 characters.
Name = Annotated[str, mapped_column(String(512), nullable=True, comment="Display name")]

#: Nullable text description.
Desc = Annotated[str, mapped_column(Text, nullable=True, comment="Description")]

#: Application-supplied UTC timestamp without an automatic value.
Timestamp = Annotated[datetime, mapped_column(DateTime, comment="Timestamp (UTC)")]

#: Indexed UTC creation time, defaulted by the database on INSERT.
Created_at = Annotated[
    datetime,
    mapped_column(
        DateTime,
        nullable=False,
        server_default=utcnow(),
        index=True,
        comment="Creation timestamp (UTC)",
    ),
]

#: Indexed UTC modification time, defaulted on INSERT and SQLAlchemy UPDATE.
Updated_at = Annotated[
    datetime,
    mapped_column(
        DateTime,
        nullable=False,
        default=utcnow(),
        server_default=utcnow(),
        onupdate=utcnow(),
        index=True,
        comment="Last update timestamp (UTC)",
    ),
]

#: IANA timezone, defaulted to the writing process's local timezone.
Timezone = Annotated[
    ZoneInfo,
    mapped_column(
        TimezoneType(backend="zoneinfo"),
        default=get_localzone_name,
        comment="Local IANA timezone",
    ),
]


class TimestampMixin:
    """UTC creation and modification timestamps."""

    created_at: Mapped[Created_at]
    updated_at: Mapped[Updated_at]


def fk(
    target: type | str,
    *,
    ondelete: str | None = None,
    onupdate: str | None = None,
    **kwargs: Any,
) -> MappedColumn[Any]:
    """Declare a foreign key to a mapped class or table's ``pk`` column.

    Parameters
    ----------
    target : type or str
        Mapped class, or table name optionally qualified by its schema.
    ondelete, onupdate : str, optional
        SQL foreign-key actions, such as ``"CASCADE"``. No cascading action is
        declared by default.
    **kwargs
        Column settings passed to ``mapped_column``, such as ``nullable`` or
        ``primary_key``. The default comment identifies the referenced key.

    Returns
    -------
    sqlalchemy.orm.MappedColumn
        Foreign-key column with the referenced key's SQL type.

    Examples
    --------
    >>> from sqlalchemy.orm import DeclarativeBase
    >>> class Base(DeclarativeBase):
    ...     pass
    >>> class Device(Base):
    ...     __tablename__ = "device"
    ...     pk: Mapped[Pk]
    >>> class Reading(Base):
    ...     __tablename__ = "reading"
    ...     pk: Mapped[Pk]
    ...     device_fk: Mapped[int] = fk(Device)
    >>> next(iter(Reading.__table__.c.device_fk.foreign_keys)).target_fullname
    'device.pk'
    """
    reference = (
        f"{target}.pk"
        if isinstance(target, str)
        else class_mapper(target, configure=False).local_table.c.pk
    )
    kwargs.setdefault("comment", f"Foreign key to {reference}")
    return mapped_column(
        ForeignKey(reference, ondelete=ondelete, onupdate=onupdate), **kwargs
    )
