"""Shared column and actor conventions in independent application schemas."""

from datetime import UTC, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import String, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tollan.db import SqlaDB
from tollan.db.mapped_types import (
    Desc,
    Label,
    Name,
    Pk,
    Timestamp,
    TimestampMixin,
    Timezone,
    Uuid,
    fk,
)
from tollan.db.orm import ActorBase, AuditMixin, batch_upsert


def test_conventions_and_model_local_label_uniqueness():
    class Base(DeclarativeBase):
        pass

    class Device(Base):
        __tablename__ = "device"
        pk: Mapped[Pk]
        label: Mapped[Label] = mapped_column(unique=True)
        category: Mapped[Label]
        name: Mapped[Name | None]
        description: Mapped[Desc | None]
        timezone: Mapped[Timezone]

    with SqlaDB.from_url("sqlite://") as db:
        Base.metadata.create_all(db.engine)
        with db.session_context() as session:
            session.add_all(
                [
                    Device(
                        label="a",
                        category="sensor",
                        name="n" * 512,
                        timezone=ZoneInfo("America/Mexico_City"),
                    ),
                    Device(label="b", category="sensor", timezone=ZoneInfo("UTC")),
                ]
            )
        with db.session_context() as session:
            devices = session.scalars(select(Device).order_by(Device.label)).all()
            assert devices[0].pk != devices[1].pk
            assert devices[0].name == "n" * 512
            assert devices[1].name is None and devices[1].description is None
            assert devices[0].timezone == ZoneInfo("America/Mexico_City")
            assert [device.category for device in devices] == ["sensor", "sensor"]
        with pytest.raises(IntegrityError), db.session_context() as session:
            session.add(Device(label="a", category="other", timezone=ZoneInfo("UTC")))
        with db.session_context() as session:
            device = session.scalars(select(Device).where(Device.label == "a")).one()
            assert device.name == "n" * 512
    assert isinstance(Device.__table__.c.name.type, String)
    assert Device.__table__.c.name.type.length == 512
    assert all(column.comment for column in Device.__table__.c)


def test_timestamp_defaults_explicit_values_and_bulk_upsert():
    class Base(DeclarativeBase):
        pass

    class Reading(TimestampMixin, Base):
        __tablename__ = "reading"
        pk: Mapped[Pk]
        label: Mapped[Label] = mapped_column(unique=True)
        value: Mapped[int]

    original = datetime(2000, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    supplied = datetime(2001, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    before = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    with SqlaDB.from_url("sqlite://") as db:
        Base.metadata.create_all(db.engine)
        with db.session_context() as session:
            session.add(
                Reading(label="a", value=1, created_at=original, updated_at=original)
            )
            session.execute(text("INSERT INTO reading (label, value) VALUES ('b', 2)"))
        with db.session_context() as session:
            first = session.scalars(select(Reading).where(Reading.label == "a")).one()
            pk = first.pk
            assert first.created_at == first.updated_at == original
            generated = session.scalars(
                select(Reading).where(Reading.label == "b")
            ).one()
            assert generated.created_at >= before and generated.updated_at >= before
            batch_upsert(
                session,
                Reading,
                [{"label": "a", "value": 3}, {"label": "c", "value": 4}],
                index_elements=[Reading.label],
            )
            session.refresh(first)
            assert first.pk == pk and first.value == 3
            assert first.created_at == original and first.updated_at >= before
            batch_upsert(
                session,
                Reading,
                [{"label": "a", "value": 5, "updated_at": supplied}],
                index_elements=["label"],
            )
            session.refresh(first)
            assert first.updated_at == supplied
        with (  # noqa: PT012 -- exercise rollback after executing the batch.
            pytest.raises(ValueError, match="rollback"),
            db.session_context() as session,
        ):
            batch_upsert(
                session,
                Reading,
                [{"label": "a", "value": 99}],
                index_elements=["label"],
            )
            msg = "rollback"
            raise ValueError(msg)
        with db.session_context() as session:
            first = session.get_one(Reading, pk)
            assert first.value == 5 and first.updated_at == supplied
            first.value = 6
        with db.session_context() as session:
            assert session.get_one(Reading, pk).updated_at >= before
            with pytest.raises(ValueError, match="empty"):
                batch_upsert(session, Reading, [], index_elements=["label"])
            with pytest.raises(ValueError, match="same column keys"):
                batch_upsert(
                    session,
                    Reading,
                    [{"label": "x"}, {"label": "y", "value": 2}],
                    index_elements=["label"],
                )


def test_uuid_generation_import_and_event_timestamp():
    class Base(DeclarativeBase):
        pass

    class Event(Base):
        __tablename__ = "event"
        pk: Mapped[Pk]
        uid: Mapped[Uuid] = mapped_column(unique=True)
        name: Mapped[Name]
        observed_at: Mapped[Timestamp | None]

    supplied_uid = uuid4()
    observed_at = datetime(2026, 10, 14, 12, tzinfo=UTC).replace(tzinfo=None)
    with SqlaDB.from_url("sqlite://") as db:
        Base.metadata.create_all(db.engine)
        with db.session_context() as session:
            event = Event(name="local", observed_at=observed_at)
            assert event.uid is None
            session.add(event)
            session.flush()
            generated_uid = event.uid
            assert isinstance(generated_uid, UUID) and generated_uid.version == 4
            session.execute(
                Event.__table__.insert(), [{"name": "batch-a"}, {"name": "batch-b"}]
            )
            session.add(Event(name="imported", uid=supplied_uid))
        with db.session_context() as session:
            events = session.scalars(select(Event)).all()
            assert len({event.uid for event in events}) == 4
            assert all(isinstance(event.uid, UUID) for event in events)
            local = session.scalars(
                select(Event).where(Event.uid == generated_uid)
            ).one()
            assert local.observed_at == observed_at
            local.name = "renamed"
            imported = session.scalars(
                select(Event).where(Event.uid == supplied_uid)
            ).one()
            assert imported.name == "imported" and imported.observed_at is None
        with db.session_context() as session:
            local = session.scalars(select(Event).where(Event.name == "renamed")).one()
            assert local.uid == generated_uid and local.observed_at == observed_at


@pytest.mark.parametrize("as_string", [True, False])
def test_foreign_key_target_and_explicit_actions(as_string):
    class Base(DeclarativeBase):
        pass

    class Device(Base):
        __tablename__ = "device"
        pk: Mapped[str] = mapped_column(String(32), primary_key=True)

    class Reading(Base):
        __tablename__ = "reading"
        device_fk: Mapped[str] = fk(
            "device" if as_string else Device,
            primary_key=True,
            ondelete="CASCADE" if as_string else None,
        )
        value: Mapped[int]

    column = Reading.__table__.c.device_fk
    assert isinstance(column.type, String)
    assert column.type.length == 32
    reference = next(iter(column.foreign_keys))
    assert reference.target_fullname == "device.pk"
    assert reference.ondelete == ("CASCADE" if as_string else None)
    assert reference.onupdate is None
    with SqlaDB.from_url("sqlite://") as db:
        Base.metadata.create_all(db.engine)
        with db.session_context() as session:
            session.add(Device(pk="sensor"))
            session.flush()
            session.add(Reading(device_fk="sensor", value=42))
        with db.session_context() as session:
            assert session.get_one(Reading, "sensor").value == 42


def test_actor_and_audit_mixins_use_application_registry():
    for index in range(2):

        class Base(DeclarativeBase):
            pass

        class Actor(ActorBase, Base):
            pass

        class Product(AuditMixin, Base):
            __tablename__ = "product"
            pk: Mapped[Pk]

        with SqlaDB.from_url("sqlite://") as db:
            Base.metadata.create_all(db.engine)
            with db.session_context() as session:
                actor = Actor(
                    uid=UUID(int=index),
                    name="site",
                    meta={"hostname": "taco", "timezone": "America/Mexico_City"},
                )
                product = Product(created_by=actor, updated_by=actor)
                session.add(product)
                session.flush()
                assert actor.pk == product.created_by_fk == product.updated_by_fk
                assert product.created_at is not None and product.updated_at is not None
            with db.session_context() as session:
                product = session.scalars(select(Product)).one()
                assert product.created_by is not None
                assert product.created_by is product.updated_by
                assert product.created_by.meta["timezone"] == "America/Mexico_City"
                assert product.created_by.uid == UUID(int=index)
                assert "updated_at" not in Actor.__table__.c
