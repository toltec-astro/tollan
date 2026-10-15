"""SQL expressions for database timestamps and date/time columns."""

import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression

__all__ = ["create_datetime", "utcnow"]


class utcnow(expression.FunctionElement):  # noqa: N801 -- SQL function spelling.
    """Database-side expression for the current UTC timestamp.

    Use in a SELECT statement or as a column's default expression. Timestamp
    precision and the returned datetime's timezone information depend on the
    database and column type.

    Examples
    --------
    Define a timestamp populated by the database when an INSERT omits it:

    >>> from sqlalchemy import Column, DateTime
    >>> created_at = Column(DateTime(), server_default=utcnow())
    """

    type = sa.DateTime()
    inherit_cache = True


@compiles(utcnow, "postgresql")
def _postgresql_utcnow(_element, _compiler, **_kw):
    return "TIMEZONE('utc', CURRENT_TIMESTAMP)"


@compiles(utcnow, "mysql")
def _mysql_utcnow(_element, _compiler, **_kw):
    return "UTC_TIMESTAMP()"


@compiles(utcnow)
def _default_utcnow(_element, _compiler, **_kw):
    return "CURRENT_TIMESTAMP"


class create_datetime(expression.FunctionElement):  # noqa: N801 -- SQL function spelling.
    """Datetime expression combining a date column and a time column.

    Parameters
    ----------
    date, time : sqlalchemy.sql.expression.ColumnElement
        SQL date and time expressions. Compiles to DATETIME for SQLite and
        TIMESTAMP for MySQL.

    Raises
    ------
    TypeError
        Compilation for SQLite requires two arguments. The default compiler
        rejects more than two arguments.
    """

    type = sa.DateTime()
    inherit_cache = True


@compiles(create_datetime, "sqlite")
def _sqlite_create_datetime(element, compiler, **kw):
    if len(element.clauses) != 2:  # noqa: PLR2004 -- date and time arguments.
        message = "create datetime only supports two arguments"
        raise TypeError(message)
    return f"DATETIME({compiler.process(element.clauses, **kw)})"


@compiles(create_datetime)
def _default_create_datetime(element, compiler, **kw):
    if len(element.clauses) > 2:  # noqa: PLR2004 -- date and time arguments.
        message = "create datetime only supports two arguments"
        raise TypeError(message)
    return f"TIMESTAMP({compiler.process(element.clauses, **kw)})"
