#!/usr/bin/env python

import numbers
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Generator, Sequence, Type, Union

from astropy.time import Time
from astropy.units import Quantity
from pydantic import BaseModel, DirectoryPath, FilePath
from pydantic_yaml import YamlModelMixin

from ..utils.general import ensure_abspath
from ..utils.yaml import yaml_dump, yaml_load

"""Common pydantic types used in config."""


__all__ = [
    "ImmutableBaseModel",
    "AbsFilePath",
    "AbsDirectoryPath",
    "TimeField",
    "quantity_field",
]


class ImmutableBaseModel(YamlModelMixin, BaseModel):
    """A common base model class for config models."""

    class Config:
        yaml_dumps = yaml_dump
        yaml_loads = yaml_load
        allow_mutation = False
        keep_untouched = (cached_property,)


def path_ensure_abspath_validator(v: Any) -> Path:
    return ensure_abspath(v)


class AbsPathMixin(object):
    @classmethod
    def __get_validators__(cls) -> Generator[Callable[..., Any], None, None]:
        yield path_ensure_abspath_validator
        yield from super().__get_validators__()  # type: ignore


class AbsFilePath(AbsPathMixin, FilePath):
    pass


class AbsDirectoryPath(AbsPathMixin, DirectoryPath):
    pass


class TimeField(Time):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update({"type": "string", "format": "date-time"})

    @classmethod
    def validate(cls, v):
        if not isinstance(v, (str, Time)):
            raise TypeError("string or Time required")
        try:
            return cls(v)
        except ValueError:
            raise ValueError("invalid time format")


class QuantityFieldBase(Quantity):
    physical_types_allowed: Union[None, str, Sequence[str]] = None

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update({"type": "string"})

    @classmethod
    def validate(cls, v):
        if not isinstance(v, (str, numbers.Number)):
            raise TypeError("string or number required")
        try:
            vv = cls(v)
        except ValueError:
            raise ValueError("invalid quantity format")
        ptypes = cls.physical_types_allowed
        if ptypes is None or not ptypes:
            return vv
        # check physical types
        if isinstance(ptypes, str):
            ptypes = [ptypes]
        if vv.unit is not None and vv.unit.physical_type not in ptypes:
            raise ValueError(
                f"quantity of {vv.unit} does not have "
                f"the required physical types {ptypes}.",
            )
        return vv


def quantity_field(
    physical_types_allowed: Union[None, str, Sequence[str]] = None,
) -> Type[Quantity]:
    # use kwargs then define conf in a dict to aid with IDE type hinting
    namespace = {"physical_types_allowed": physical_types_allowed}
    return type("QuantityField", (QuantityFieldBase,), namespace)
