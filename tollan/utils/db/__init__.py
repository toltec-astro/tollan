#! /usr/bin/env python

from ..namespace import Namespace
from schema import Schema, Optional, Use
import sqlalchemy as sa


class TableDef(Namespace):
    """A class that holds definitions to a table."""

    _namespace_from_dict_schema = Schema({
        'name': str,
        Optional('desc', default=None): str,
        'columns': Schema([sa.sql.schema.SchemaItem, ]),
        Optional('data'): [dict, ],
        str: object
        })


class SqlADB(Namespace):
    """A class that provide access to database related entities
    similar to that of `flask_sqlalchemy.SQLAlchemy`.

    """
    pass


def init_db(db, table_defs):
    """Setup table defined in table_defs in `db`.

    .. note::

        The :mete:`db.metadata.create_all` is not called.

    Parameters
    ----------
    db : `~tollan.utils.db.SqlADB` or `flask_sqlalchemy.SQLAlchemy`
        The db instance to which this table is added.
    """
    table_defs = Schema([Use(TableDef.from_dict), ]).validate(table_defs)
    for t in table_defs:
        sa.Table(t.name, db.metadata, *t.columns, comment=t.desc)
