#!/usr/bin/env python

from __future__ import annotations

from pathlib import Path

import astropy.units as u
from astropy.time import Time
from pydantic import Field

from tollan.config.types import (
    AbsDirectoryPath,
    AbsFilePath,
    ImmutableBaseModel,
    TimeField,
    quantity_field,
)
from tollan.utils.log import logger


def test_types():
    class TestModel(ImmutableBaseModel):
        """A model to test `tollan.config.types`."""

        path0: AbsFilePath = Field(default=__file__)
        path1: AbsDirectoryPath = Field(default="~")
        time: TimeField = Field(default_factory=TimeField.now)
        length: quantity_field("length") = Field(default="10m")

        class Config:
            validate_all = True

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
    assert m.length == 10 << u.m
