import tzlocal
from sqlalchemy.orm import Mapped, mapped_column, relationship

import tollan.db.mapped_types as mtypes
from tollan.db import SqlaDB
from tollan.db.orm import BetterDeclarativeBase, ClientInfoMixin, SqlaORM
from tollan.utils.sys import get_hostname


class Base(BetterDeclarativeBase):
    __abstract__ = True


class ClientInfo(Base, ClientInfoMixin):
    pass


orm = SqlaORM(Base=Base, ClientInfo=ClientInfo)


class Parent(Base):
    __tablename__ = "parent_table"

    pk: Mapped[mtypes.Pk] = mapped_column(init=False)
    children: Mapped[list["Child"]] = relationship(
        back_populates="parent",
        default_factory=list,
    )


class Child(Base):
    __tablename__ = "child_table"

    pk: Mapped[mtypes.Pk] = mapped_column(init=False)
    parent_pk: Mapped[int] = mtypes.fk(Parent, default=None)
    parent: Mapped["Parent"] = relationship(back_populates="children", default=None)


def create_db():
    db = SqlaDB.from_url(
        "sqlite://",
        engine_options={
            "echo": True,
        },
    )
    db.init_orm(orm)
    return db


def test_client_info():
    db = create_db()
    with db.session_context():
        client_info, created = orm.ClientInfo.get_or_create(name="test_client_info")
    assert created
    assert client_info.name == "test_client_info"
    assert client_info.timezone.key == tzlocal.get_localzone_name()
    assert client_info.hostname == get_hostname()


def test_relation():
    db = create_db()
    with db.session_context():
        p0, created = Parent.get_or_create()
        assert created
        assert p0.pk == 1
        assert p0.children == []
    with db.session_context() as session:
        p1 = Parent(
            children=[
                Child(),
                Child(),
            ],
        )
        session.add(p1)
    assert p1.children[0].pk == 1
    assert p1.children[1].pk == 2
    assert p1.children[0].parent_pk == 2
    assert p1.children[0].parent is p1

    with db.session_context() as session:
        c3 = Child(parent=p0)
        session.add(c3)
    assert c3.pk == 3
    assert c3.parent_pk == 1
    assert c3.parent == p0
    assert p0.children == [c3]

    with db.session_context():
        pp0, created = Parent.get_or_create(pk=1)
        assert not created
        assert pp0 == p0

        cc3, created = Child.get_or_create(pk=3)
        assert not created
        assert cc3.parent == p0


def test_workflow():

    class WF(orm.WorkflowBase):
        pass

    db = create_db()
    wf = WF(db=db)
    assert wf.client_info.pk == 1
    assert wf.client_info.hostname == get_hostname()
