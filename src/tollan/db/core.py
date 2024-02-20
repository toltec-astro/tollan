from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Session as Session_cls
from sqlalchemy.orm import scoped_session, sessionmaker

if TYPE_CHECKING:
    from .orm import SqlaORM

__all__ = [
    "SqlaDB",
]


@dataclass
class SqlaDB:
    """The class to manage SQLAlchemey connection."""

    engine: sa.Engine
    """The sqla engine."""

    metadata: sa.MetaData
    """The sqla metadata."""

    Session: sessionmaker
    """The session maker."""

    session: Session_cls
    """The session."""

    @property
    def tables(self):
        """The tables in the DB."""
        return self.metadata.tables

    def reflect_tables(self):
        """Relfect tables from DB."""
        self.metadata.reflect(bind=self.engine)

    @classmethod
    def from_url(cls, url, engine_options=None):
        """Return DB from URL."""
        engine = sa.create_engine(url, **(engine_options or {}))
        metadata = sa.MetaData()
        Session = sessionmaker(bind=engine)  # noqa: N806
        session = scoped_session(Session)
        return cls(engine=engine, metadata=metadata, Session=Session, session=session)

    @classmethod
    def from_flask_sqla(cls, db, bind=None):
        """Return DB from Flask DB."""
        engine = db.engines[bind]
        metadata = db.metadatas[bind]
        Session = sessionmaker(bind=engine)  # noqa: N806
        session = scoped_session(options={"bind": engine})
        return cls(engine=engine, metadata=metadata, Session=Session, session=session)

    @contextmanager
    def session_context(self):
        """Provide a transactional scope around a series of operations."""
        session = self.session
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def init_orm(self, orm: "SqlaORM"):
        """Set ORM with this database."""
        orm.Base.metadata.create_all(self.engine)
        orm.Base.set_session(self.session)
        # update the database table info table
        reg = orm.Base.registry
        data = []
        for mapper in reg.mappers:
            t = mapper.local_table
            data.append(
                {
                    "name": t.name,
                    "desc": t.comment or "",
                },
            )
        with self.session_context():
            orm.DatabaseTableInfo.batch_upsert(
                data,
                index_elements=[
                    "name",
                ],
            )
