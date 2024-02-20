import datetime
import zoneinfo
from typing import Annotated

import tzlocal
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column
from sqlalchemy_utils import TimezoneType

from .func import utcnow

__all__ = [
    "Pk",
    "Label",
    "Name",
    "Desc",
    "Created_at",
    "Updated_at",
    "Timezone",
    "fk",
    "TimestampMixin",
]

Pk = Annotated[int, mapped_column(Integer, primary_key=True, comment="The primary key")]

Label = Annotated[
    str,
    mapped_column(
        String(128),
        nullable=False,
        unique=True,
        sqlite_on_conflict_unique="REPLACE",
        comment="The short descriptive label.",
    ),
]

Name = Annotated[str, mapped_column(String(128), comment="The name.")]

Desc = Annotated[str, mapped_column(Text, comment="The long description.")]

Created_at = Annotated[
    datetime.datetime,
    mapped_column(
        DateTime,
        nullable=False,
        default=utcnow(),
        comment="The datetime of creation.",
    ),
]

Updated_at = Annotated[
    datetime.datetime,
    mapped_column(
        DateTime,
        nullable=False,
        default=utcnow(),
        onupdate=utcnow(),
        comment="The datetime of last modification.",
    ),
]

Timezone = Annotated[
    zoneinfo.ZoneInfo,
    mapped_column(
        TimezoneType(backend="zoneinfo"),
        default=tzlocal.get_localzone_name,
        comment="The local timezone.",
    ),
]


def fk(other, name=None, **kwargs):
    """Return mapped foreign key to `other` table."""
    if not isinstance(other, str) and hasattr(other, "__tablename__"):
        other = other.__tablename__
    else:
        raise TypeError(f"invalid type for {other}")
    if name is None:
        name = f"{other}_pk"
    kwargs.setdefault("comment", f"The shared primary key from {other}.")
    return mapped_column(
        ForeignKey(
            f"{other}.pk",
            onupdate="cascade",
            ondelete="cascade",
        ),
        **kwargs,
    )


class TimestampMixin(MappedAsDataclass):
    """The timestamp info."""

    created_at: Mapped[Created_at] = mapped_column(repr=False, init=False)
    updated_at: Mapped[Updated_at] = mapped_column(repr=False, init=False)
