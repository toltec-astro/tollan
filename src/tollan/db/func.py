import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression

__all__ = [
    "utcnow",
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
