import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression

__all__ = [
    "utcnow",
    "create_datetime",
]


class utcnow(expression.FunctionElement):  # noqa: N801, D101
    type = sa.DateTime()


@compiles(utcnow, "postgresql")
def pg_utcnow(_element, _compiler, **_kw):
    return "TIMEZONE('utc', CURRENT_TIMESTAMP)"


@compiles(utcnow, "mssql")
def ms_utcnow(_element, _compiler, **_kw):
    return "GETUTCDATE()"


@compiles(utcnow, "mysql")
def my_utcnow(_element, _compiler, **_kw):
    return "UTC_TIMESTAMP()"


@compiles(utcnow)
def default_sql_utcnow(_element, _compiler, **_kw):
    return "CURRENT_TIMESTAMP"


class create_datetime(expression.FunctionElement):  # noqa: N801
    """Return datetime from date and time column."""

    type = sa.DateTime()
    inherit_cache = True


@compiles(create_datetime, "sqlite")
def sqlite_create_datetime(element, compiler, **kw):
    if len(element.clauses) != 2:  # noqa: PLR2004
        raise TypeError("create datetime only supports two arguments")
    return f"DATETIME({compiler.process(element.clauses, **kw)})"


@compiles(create_datetime)
def default_create_datetime(element, compiler, **kw):
    if len(element.clauses) > 2:  # noqa: PLR2004
        raise TypeError("create datetime only supports two arguments")
    return f"TIMESTAMP({compiler.process(element.clauses, **kw)})"
