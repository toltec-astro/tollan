from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import sqlalchemy.exc as sae
import tzlocal
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import DeclarativeBase as _DeclarativeBase
from sqlalchemy.orm import Mapped, MappedAsDataclass
from sqlalchemy.orm import Session as Session_cls
from sqlalchemy.orm import declared_attr, mapped_column, relationship

from ..dataclasses import get_dataclass_field_default, get_dataclass_fields
from ..general import classproperty_readonly
from ..log import logger
from ..sys import get_hostname
from . import mapped_types as mtypes

if TYPE_CHECKING:
    from . import SqlaDB

__all__ = ["BetterDeclarativeBase", "SqlaORM"]


class BetterDeclarativeBase(_DeclarativeBase, MappedAsDataclass):
    """A enhanced declarative base."""

    __abstract__ = True
    _session: ClassVar[None | Session_cls] = None

    @declared_attr.directive
    @classmethod
    def __table_args__(cls):
        return {"comment": cls.__doc__}

    @classmethod
    def set_session(cls, session):
        """Set active session."""
        cls._session = session

    @classproperty_readonly
    def session(cls):
        """The active session."""
        if cls._session is not None:
            return cls._session
        raise ValueError("session is not set.")

    @classmethod
    def query(cls, session=None):
        """Return the ORM query."""
        session = session or cls.session
        return session.query(cls)

    @classmethod
    def get_or_create(
        cls,
        create_method="",
        create_method_kwargs=None,
        session: None | Session_cls = None,
        **kwargs,
    ):
        """Get or create an object from database."""
        session = session or cls.session
        try:
            return session.query(cls).filter_by(**kwargs).one(), False
        except sae.NoResultFound:
            kwargs.update(create_method_kwargs or {})
            try:
                with session.begin_nested():
                    created = getattr(cls, create_method, cls)(**kwargs)
                    session.add(created)
            except sae.IntegrityError:
                return session.query(cls).filter_by(**kwargs).one(), False
            else:
                return created, True

    @classmethod
    def batch_upsert(cls, data, index_elements, session: None | Session_cls = None):
        """Do batch upsert to database."""
        if not data:
            raise ValueError("data cannot be empty.")
        stmt = sqlite.insert(cls).values(data)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={
                k: getattr(stmt.excluded, k) for k in data[0] if k not in index_elements
            },
        )
        session = session or cls.session
        return session.execute(stmt)


class _DatabaseTableInfoMixin(MappedAsDataclass):
    """The database table info."""

    __tablename__ = "database_table_info"
    pk: Mapped[mtypes.Pk] = mapped_column(init=False)
    name: Mapped[mtypes.Label] = mapped_column(comment="The table name.")
    desc: Mapped[mtypes.Desc] = mapped_column(comment="The table description.")


class ClientInfoMixin(mtypes.TimestampMixin, MappedAsDataclass):
    """The client info."""

    __tablename__ = "client_info"
    pk: Mapped[mtypes.Pk] = mapped_column(init=False)
    name: Mapped[mtypes.Name] = mapped_column(
        nullable=False,
        default="default",
        comment="The client name.",
    )
    hostname: Mapped[mtypes.Name] = mapped_column(
        default_factory=get_hostname,
        comment="The client hostname.",
    )
    timezone: Mapped[mtypes.Timezone] = mapped_column(
        default_factory=tzlocal.get_localzone_name,
        comment="The client timezone.",
    )

    @classmethod
    def get_or_create(cls, name=None, hostname=None, session=None):
        """Get or create client info."""
        fields = get_dataclass_fields(cls, "name", "hostname")
        name = name or get_dataclass_field_default(fields["name"])
        hostname = hostname or get_dataclass_field_default(fields["hostname"])
        return super(BetterDeclarativeBase, cls).get_or_create(
            name=name,
            hostname=hostname,
            session=session,
        )


class _ClientInfoRefMixin(MappedAsDataclass):
    """A mixin class to include client info relation."""

    _client_info_cls: ClassVar[type[ClientInfoMixin]]

    @declared_attr
    @classmethod
    def client_info_pk(cls) -> Mapped[int]:
        return mtypes.fk(
            cls._client_info_cls,
            repr=False,
            default=None,
            comment="The client info id.",
        )

    @declared_attr
    @classmethod
    def client_info(cls) -> Mapped:
        return relationship(cls._client_info_cls, default=None)


class _SqlaORMWorkflow:
    """A base class to define database based workflows."""

    orm: ClassVar["SqlaORM"]
    db: "SqlaDB"
    client_info: BetterDeclarativeBase

    def __init__(self, db: "SqlaDB", client_name: None | str = None):
        # validate that db has the correct protocal
        if not hasattr(db, "init_orm"):
            raise ValueError(f"invalid database {db=}")
        self.db = db
        self.db.init_orm(self.orm)
        with self.db.session_context():
            client_info, _ = self.orm.get_or_create_client_info(
                name=client_name or self.__class__.__name__.lower(),
            )
            self.client_info = client_info


@dataclass
class SqlaORM:
    """The class to manage a the ORM classes."""

    Base: type[BetterDeclarativeBase]
    ClientInfo: type[BetterDeclarativeBase]

    ClientInfoRefMixin: type[BetterDeclarativeBase] = field(init=False)
    DatabaseTableInfo: type[BetterDeclarativeBase] = field(init=False)

    WorkflowBase: type[_SqlaORMWorkflow] = field(init=False)

    def __post_init__(self):
        self.ClientInfoRefMixin = type(
            "ClientInfoRefMixin",
            (_ClientInfoRefMixin, MappedAsDataclass),
            {
                "__doc__": _ClientInfoRefMixin.__doc__,
                "_client_info_cls": self.ClientInfo,
            },
        )
        self.DatabaseTableInfo = type(
            "DatabaseTableInfo",
            (self.Base, _DatabaseTableInfoMixin),
            {"__doc__": _DatabaseTableInfoMixin.__doc__},
        )
        self.WorkflowBase = type(
            "WorkflowBase",
            (_SqlaORMWorkflow,),
            {
                "__doc__": _SqlaORMWorkflow.__doc__,
                "orm": self,
            },
        )

    def get_or_create_client_info(self, name):
        """Get or create a client info object."""
        client_info, created = self.ClientInfo.get_or_create(name=name)
        if created:
            logger.debug(f"create new client info {client_info}")
        else:
            logger.debug(f"get client info {client_info}")
        return client_info, created
