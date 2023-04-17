from __future__ import annotations

import json
from pathlib import Path

import astropy.units as u
from astropy.time import Time
from pydantic import Field

from tollan.config.types import (
    AbsAnyPath,
    AbsDirectoryPath,
    AbsFilePath,
    AnyPath,
    ImmutableBaseModel,
    QuantityField,
    TimeField,
    create_list_model,
    quantity_field,
    time_field,
)
from tollan.utils.log import logger

DatetimeField = time_field("datetime")
MjdField = time_field("mjd")
IsotField = time_field("isot")
LengthField = quantity_field("length")
DurationField = quantity_field("time")
MassField = quantity_field("mass")


class SimpleModel(ImmutableBaseModel):
    """A model to test `tollan.config.types`."""

    path0: AbsFilePath = Field(default=__file__, strict=False)
    path1: AbsDirectoryPath = Field(default="~", strict=False)
    time0: DatetimeField = Field(
        default_factory=TimeField.now,
    )
    time1: MjdField = Field(
        default=TimeField(55000, format="mjd"),
    )
    time2: IsotField = Field(
        default="2022-02-02T02:02:02",
    )
    length: LengthField = Field(default="10m")
    duration: DurationField = Field(default="10yr")
    mass: MassField = Field(default=10 << u.g)
    dimless: QuantityField = Field(default=1)


def test_types():
    m = SimpleModel.model_validate({})
    logger.debug(f"m.model_json_schema:\n{json.dumps(m.model_json_schema(), indent=2)}")
    logger.debug(f"m:\n{m}")
    logger.debug(f"m.model_dump:\n{m.model_dump()}")
    logger.debug(f"m.model_dump_json:\n{m.model_dump_json(indent=2)}")
    logger.debug(f"m.model_dump_yaml:\n{m.model_dump_yaml()}")
    assert isinstance(m.path0, Path)
    assert m.path0.is_absolute()
    assert isinstance(m.path1, Path)
    assert m.path1.is_absolute()
    assert m.path1.is_dir()
    assert isinstance(m.time0, Time)
    assert m.time0 < Time.now()
    assert isinstance(m.length, u.Quantity)
    assert m.length.unit is u.m
    assert m.length == 10 << u.m  # type: ignore

    assert isinstance(m.duration, u.Quantity)
    assert m.duration.unit is u.year
    assert m.duration == 10 << u.year  # type: ignore

    assert isinstance(m.mass, u.Quantity)
    assert m.mass.unit is u.g
    assert m.mass == 10 << u.g

    assert isinstance(m.dimless, u.Quantity)
    assert m.dimless.unit is u.dimensionless_unscaled
    assert m.dimless == 1


class SimpleModel2(ImmutableBaseModel):
    """A model to test `tollan.config.types`."""

    path0: AbsAnyPath = Field(default="a")
    path1: AnyPath = Field(default="a")


def test_abspath_rootpath():
    m = SimpleModel2.model_validate({}, context={"rootpath": "~"})
    logger.debug(f"m.model_json_schema:\n{json.dumps(m.model_json_schema(), indent=2)}")
    logger.debug(f"m:\n{m}")
    logger.debug(f"m.model_dump:\n{m.model_dump()}")
    logger.debug(f"m.model_dump_yaml:\n{m.model_dump_yaml()}")

    assert m.path0.is_absolute()
    assert m.path0 == Path("~/a").expanduser()
    assert not m.path1.is_absolute()
    assert m.path1 == Path("~/a")


class Nested(ImmutableBaseModel):
    path0: AbsAnyPath = Field(default="a")


Nested1 = create_list_model("Nested1", item_model_cls=Nested)


class Nested2(ImmutableBaseModel):
    """A model to test `tollan.config.types`."""

    nested: Nested1  # type: ignore


def test_context_nested():
    # Nested2.update_forward_refs(Nested1=Nested1, Nested=Nested)
    m = Nested2.model_validate(
        {"nested": [{}, {"path0": "b"}]},
        context={"rootpath": "~"},
    )

    logger.debug(f"m.model_json_schema:\n{json.dumps(m.model_json_schema(), indent=2)}")
    logger.debug(f"m:\n{m}")
    logger.debug(f"m.model_dump:\n{m.model_dump()}")
    logger.debug(f"m.model_dump_yaml:\n{m.model_dump_yaml()}")

    assert m.nested[0].path0.is_absolute()
    assert m.nested[0].path0 == Path("~/a").expanduser()
