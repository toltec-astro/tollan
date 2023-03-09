#!/usr/bin/env python

import builtins
import collections.abc
import numbers
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar, Dict, Sequence, Type, Union

from astropy.time import Time
from astropy.units import Quantity
from pydantic import BaseModel, DirectoryPath, FilePath, validator, validators
from pydantic_yaml import YamlModelMixin

from ..utils.yaml import yaml_dump, yaml_load

"""Common pydantic types used in config."""


__all__ = [
    "ImmutableBaseModel",
    "TimeField",
    "quantity_field",
    "path_field",
    "AbsFilePath",
    "AbsDirectoryPath",
    "AbsAnyPath",
    "AnyPath",
]


class ContextfulBaseModelMeta(type(BaseModel)):
    """A custom metaclass to support attaching context to models."""

    _context_key = "validation_context"
    _root_key = "__root__"

    def __new__(cls, name, bases, namespace, **kwargs):
        context_key = cls._context_key
        root_key = cls._root_key
        # this creates the validation
        anno_new = {}
        namespace_new = {"__annotations__": anno_new}
        if (
            root_key not in namespace
            and root_key not in namespace.get("__annotations__", {})
            and name != "ImmutableBaseModel"
        ):
            namespace_new[context_key] = None  # type: ignore
            anno_new[context_key] = Any
        for k, v in namespace.items():
            if k == "__annotations__":
                anno_new.update(v)
            else:
                namespace_new[k] = v
        return super().__new__(cls, name, bases, namespace_new, **kwargs)


class ImmutableBaseModel(YamlModelMixin, BaseModel, metaclass=ContextfulBaseModelMeta):
    """A common base model class for config models."""

    _context_key: ClassVar = ContextfulBaseModelMeta._context_key
    _root_key: ClassVar = ContextfulBaseModelMeta._root_key

    class Config:
        yaml_dumps = yaml_dump
        yaml_loads = yaml_load
        allow_mutation = False
        keep_untouched = (cached_property,)
        validate_all = True

    @validator("*", each_item=True, pre=True)
    def _add_context(cls, value, values, field):
        context_key = cls._context_key
        root_key = cls._root_key
        if field.name == context_key or context_key not in values:
            return value
        ctx = values[context_key]
        field.field_info.extra[context_key] = ctx

        # propagate ctx down
        def _get_nested_list_item_field(f):
            # infer child field for list value
            t = f.type_
            if root_key not in t.__fields__:
                return None
            item_type = t.__fields__[root_key].type_
            if issubclass(item_type, ImmutableBaseModel):
                return t.__fields__[root_key]
            return None

        def _inject_ctx(v, f):
            print(f"inject field {f} {v=}")

            if isinstance(v, collections.abc.Mapping) and issubclass(
                f.type_, ImmutableBaseModel
            ):
                v[context_key] = ctx  # type: ignore
            elif isinstance(v, list):
                item_field = _get_nested_list_item_field(f)
                if item_field is not None:
                    for vv in v:
                        _inject_ctx(vv, item_field)  # type: ignore
            else:
                pass

        _inject_ctx(value, field)
        return value

    def _calculate_keys(self, include, exclude, exclude_unset):
        context_key = self._context_key
        exclude = exclude or {}
        exclude[context_key] = ...
        return super()._calculate_keys(
            include=include, exclude=exclude, exclude_unset=exclude_unset
        )


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
    namespace = {"physical_types_allowed": physical_types_allowed}
    return type("QuantityField", (QuantityFieldBase,), namespace)


class PathFieldBase(Path):
    type: Union[None, str] = None
    exists: bool = True
    resolve: bool = True

    _type_dispatch = {
        None: {"format": "path", "validator": None},
        "file": {"format": "file-path", "validator": FilePath.validate},  # type: ignore
        "dir": {"format": "directory-path", "validator": DirectoryPath.validate},  # type: ignore
    }

    @classmethod
    def __modify_schema__(cls, field_schema: Dict[str, Any]) -> None:
        field_schema.update(format=cls._type_dispatch[cls.type]["format"])

    @classmethod
    def __get_validators__(cls):
        yield cls.validate_rootpath
        yield validators.path_validator
        if cls.resolve:
            yield cls.resolve_path
        if cls.exists:
            yield validators.path_exists_validator
        type_validator = cls._type_dispatch[cls.type]["validator"]
        if type_validator is not None:
            yield type_validator

    @classmethod
    def validate_rootpath(cls, value, field):
        ctx = field.field_info.extra.get("validation_context", None) or {}
        if "rootpath" in ctx:
            value = Path(ctx["rootpath"]).joinpath(value)
        return value

    @classmethod
    def resolve_path(cls, value):
        return value.expanduser().resolve()


def path_field(
    type: Union[None, str] = None, exists: bool = False, resolve: bool = False
) -> Type[Path]:
    namespace = {"type": type, "exists": exists, "resolve": resolve}
    return builtins.type("PathField", (PathFieldBase,), namespace)


AnyPath = PathField = path_field(type=None, exists=False, resolve=False)
"""A field for any path."""

AbsDirectoryPath = path_field(type="dir", resolve=True)
"A field for resolved, existing directory path."

AbsFilePath = path_field(type="file", resolve=True)
"A field for resolved, existing file path."

AbsAnyPath = path_field(type=None, exists=False, resolve=True)
"A field for resolved path."
