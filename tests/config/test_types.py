from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import astropy.units as u
from astropy.time import Time
from pydantic import Field

from tollan.config.types import (
    AbsAnyPath,
    AbsDirectoryPath,
    AbsFilePath,
    AnyPath,
    ImmutableBaseModel,
    TimeField,
    quantity_field,
)
from tollan.utils.log import logger


def test_types():
    class TestModel(ImmutableBaseModel):
        """A model to test `tollan.config.types`."""

        if TYPE_CHECKING:
            path0: Path
            path1: Path
            time: u.Quantity
            length: u.Quantity
        else:
            path0: AbsFilePath = Field(default=__file__)
            path1: AbsDirectoryPath = Field(default="~")
            time: TimeField = Field(default_factory=TimeField.now)
            length: quantity_field("length") = Field(default="10m")

    m = TestModel.parse_obj({})
    logger.debug(f"m.schema:\n{m.schema_json(indent=2)}")
    logger.debug(f"m:\n{m}")
    logger.debug(f"m.dict:\n{m.dict()}")
    logger.debug(f"m.yaml:\n{m.yaml()}")
    assert isinstance(m.path0, Path)
    assert m.path0.is_absolute()
    assert isinstance(m.path1, Path)
    assert m.path1.is_absolute()
    assert m.path1.is_dir()
    assert isinstance(m.time, Time)
    assert m.time < Time.now()
    assert isinstance(m.length, u.Quantity)
    assert m.length.unit is u.m
    assert m.length == 10 << u.m  # type: ignore


def test_abspath_rootpath():
    class TestModel(ImmutableBaseModel):
        """A model to test `tollan.config.types`."""

        if TYPE_CHECKING:
            path0: Path
            path1: Path
        else:
            path0: AbsAnyPath = Field(default="a")
            path1: AnyPath = Field(default="a")

    m = TestModel.parse_obj({"validation_context": {"rootpath": "~"}})
    logger.debug(f"m.schema:\n{m.schema_json(indent=2)}")
    logger.debug(f"m:\n{m}")
    logger.debug(f"m.dict:\n{m.dict()}")
    logger.debug(f"m.yaml:\n{m.yaml()}")
    assert m.path0.is_absolute()
    assert m.path0 == Path("~/a").expanduser()
    assert not m.path1.is_absolute()
    assert m.path1 == Path("~/a")


class Nested(ImmutableBaseModel):
    if TYPE_CHECKING:
        path0: Path
    else:
        path0: AbsAnyPath = Field(default="a")


class Nested1(ImmutableBaseModel):
    __root__: list[Nested]

    def __iter__(self):
        return iter(self.__root__)

    def __getitem__(self, item):
        return self.__root__[item]


class Nested2(ImmutableBaseModel):
    """A model to test `tollan.config.types`."""

    nested: Nested1


def test_context_nested():
    Nested2.update_forward_refs(Nested1=Nested1, Nested=Nested)

    m = Nested2.parse_obj({"validation_context": {"rootpath": "~"}, "nested": [{}]})
    logger.debug(f"m.schema:\n{m.schema_json(indent=2)}")
    logger.debug(f"m:\n{m}")
    logger.debug(f"m.dict:\n{m.dict()}")
    logger.debug(f"m.yaml:\n{m.yaml()}")
    assert m.nested[0].path0.is_absolute()
    assert m.nested[0].path0 == Path("~/a").expanduser()
