#! /usr/bin/env python

from ..namespace import Namespace
from schema import Schema, Optional, Use
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy import MetaData
from wrapt import ObjectProxy


__all__ = ['TableDef', 'TableDefList', 'SqlaDB']


class TableDef(Namespace):
    """A class that holds definitions to a table."""

    _namespace_from_dict_schema = Schema({
        'name': str,
        Optional('desc', default=None): str,
        'columns': Schema([sa.sql.schema.SchemaItem, ]),
        Optional('data'): [dict, ],
        str: object
        })

    def init_table(self, db):
        """Setup table metadata for this table def in `db`.

        Parameters
        ----------
        db : `~tollan.utils.db.SqlaDB` or `~flask_sqlalchemy.SQLAlchemy`
            The db instance to which this table is added.
        """
        return sa.Table(
                self.name, db.metadata, *self.columns, comment=self.desc)


class TableDefList(ObjectProxy):
    def __init__(self, table_defs):
        super().__init__(
                Schema([Use(TableDef.from_dict), ]).validate(table_defs))

    def init_db(self, db):
        """Setup tables defined in this `~tollan.utils.TableDefList` in `db`.

        .. note::

            The :meth:`db.metadata.create_all` is not called.

        Parameters
        ----------
        db : `~tollan.utils.db.SqlaDB` or `~flask_sqlalchemy.SQLAlchemy`
            The db instance to which this table is added.
        """
        for t in self:
            t.init_table(db)


class SqlaDB(Namespace):
    """A class that provide access to database related entities
    similar to that of `flask_sqlalchemy.SQLAlchemy`.

    """
    @classmethod
    def from_uri(cls, uri, engine_options=None):
        engine = sa.create_engine(uri, **engine_options)
        metadata = sa.MetaData(bind=engine)
        Session = sessionmaker(bind=engine)
        return cls(engine=engine, metadata=metadata, Session=Session)

    @property
    def tables(self):
        return self.metadata.tables

    @classmethod
    def from_flask_sqla(cls, db, bind=None):
        engine = db.get_engine(bind=bind)
        metadata = MetaData()
        Session = sessionmaker(bind=engine)
        session = db.create_scoped_session(
            options={'bind': engine})
        return cls(
                engine=engine, metadata=metadata,
                Session=Session, session=session)

    def reflect_tables(self):
        self.metadata.reflect(bind=self.engine)
