import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression


class utcnow(expression.FunctionElement):  # noqa: N801, D101
    type = sa.DateTime()


@compiles(utcnow, "postgresql")
def pg_utcnow(_element, _compiler, **_kw):  # noqa: D103
    return "TIMEZONE('utc', CURRENT_TIMESTAMP)"


@compiles(utcnow, "mssql")
def ms_utcnow(_element, _compiler, **_kw):  # noqa: D103
    return "GETUTCDATE()"


@compiles(utcnow, "mysql")
def my_utcnow(_element, _compiler, **_kw):  # noqa: D103
    return "UTC_TIMESTAMP()"


@compiles(utcnow)
def default_sql_utcnow(_element, _compiler, **_kw):  # noqa: D103
    return "CURRENT_TIMESTAMP"
