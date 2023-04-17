import dataclasses
import numbers
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, TypedDict, cast

from astropy.time import Time
from astropy.units import Quantity
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    model_serializer,
    root_validator,
)
from pydantic.types import PathType as _PathType
from pydantic_core import PydanticCustomError, core_schema

from ..utils.yaml import yaml_dump, yaml_load

__all__ = [
    "ImmutableBaseModel",
    "TimeField",
    "time_field",
    "IsoTimeField",
    "UnixTimeField",
    "QuantityField",
    "quantity_field",
    "LengthQuantityField",
    "AngleQuantityField",
    "TimeQuantityField",
    "DimensionlessQuantityField",
    "AnyPath",
    "AbsAnyPath",
    "AbsFilePath",
    "AbsDirectoryPath",
    "create_list_model",
]


class ImmutableBaseModel(BaseModel):
    """A common base model class."""

    yaml_load: ClassVar = staticmethod(yaml_load)
    yaml_dump: ClassVar = staticmethod(yaml_dump)

    model_config = ConfigDict(
        frozen=True,
        validate_default=True,
        ignored_types=(cached_property,),
        strict=True,
        # arbitrary_types_allowed=True,
    )

    def model_dump_yaml(self, **kwargs):
        """Dump model as yaml."""
        d = self.model_dump(**kwargs)
        return self.yaml_dump(d)

    @classmethod
    def model_validate_yaml(cls, yaml_source, **kwargs):
        """Validate model from yaml."""
        d = cls.yaml_load(yaml_source)
        return cls.model_validate(d, **kwargs)


class DeferredValidationFieldMixin:
    """An adaptor class to implement custom pydantic fields with constraints."""

    @classmethod
    def __pydantic_modify_json_schema__(
        cls,
        _field_schema: TypedDict,
    ) -> TypedDict:
        return core_schema.any_schema()

    @classmethod
    def __get_pydantic_core_schema__(cls, **_kwargs) -> core_schema.CoreSchema:
        return core_schema.any_schema()


class _SimpleTypeValidatorMixin:
    """A mixin class for custom type validation."""

    _field_type: ClassVar[type]
    _field_type_name: ClassVar[str]
    _field_type_error_message: ClassVar[str]
    _field_value_types: ClassVar[set]

    _field_value_schema_stub: dict[str, Any]
    _field_value_error_message: str

    def __init_subclass__(cls):
        if cls._field_type not in cls._field_value_types:
            cls._field_value_types.add(cls._field_type)

    def __pydantic_modify_json_schema__(
        self,
        field_schema: dict[str, Any],
    ) -> dict[str, Any]:
        field_schema.update(self._field_value_schema_stub)
        return field_schema

    def __get_pydantic_core_schema__(
        self,
        schema: core_schema.CoreSchema,
        **_kwargs,
    ) -> core_schema.AfterValidatorFunctionSchema:
        return core_schema.field_after_validator_function(
            self._field_validate,
            schema=schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                self._field_serialize,
            ),
        )

    def _field_serialize(self, value):
        return str(value)

    def _field_validate(self, value, info):
        # validate type first
        value = self._field_validate_type(value, info)
        # do construction
        value = self._field_construct_value(value, info)
        # do post check
        return self._field_validate_value(value, info)

    def _field_validate_type(self, value, *_args, **_kwargs):
        """Return validate custom type."""
        if not isinstance(value, tuple(self._field_value_types)):
            raise PydanticCustomError(
                f"invalid_{self._field_type_name}_type",
                self._field_type_error_message.format(type=type(value)),
            )
        return value

    def _field_construct_value(self, value, *_args, **kwargs):
        try:
            field_construct_kw = kwargs.get("field_construct_kw", {})
            return self._field_type(value, **field_construct_kw)
        except ValueError as e:
            raise PydanticCustomError(
                f"invalid_{self._field_type_name}_arg",
                self._field_value_error_message.format(value=value),
            ) from e

    def _field_validate_value(self, value, *_args, **_kwargs):
        return value


@dataclasses.dataclass
class TimeValidator(_SimpleTypeValidatorMixin):
    """The constraints for validating `astropy.time.Time`."""

    formats_allowed: None | str | Sequence[str] = None

    _field_type: ClassVar = Time
    _field_type_name: ClassVar = "Time"
    _field_type_error_message: ClassVar = (
        "Time or datatime string is required, got {type}."
    )
    _field_value_types: ClassVar = {numbers.Number, str}

    @cached_property
    def _field_formats(self):
        fmts = self.formats_allowed
        if not fmts:
            return None
        if isinstance(fmts, str):
            return (fmts,)
        return fmts

    @cached_property
    def _field_value_schema_stub(self):
        schema: dict[str, Any] = {
            "type": "string",
            "format": "date-time",
        }
        fmts = self._field_formats
        if fmts is None:
            return schema
        schema["time_formats_allowed"] = fmts
        return schema

    def _field_serialize(self, value):
        return value.isot

    @cached_property
    def _field_value_error_message(self):
        if self.formats_allowed is None:
            return "Invalid time format: {value}"
        return f"Time formats {self.formats_allowed} required, got {{value}}"

    def _field_construct_value(self, value, *args, **kwargs):
        """Return `astropy.time.Time`."""
        formats = self.formats_allowed
        if not formats:
            return super()._field_construct_value(value, *args, **kwargs)
        # here we construct the type with explicit formats
        if isinstance(formats, str):
            formats = [formats]
        for format in formats:
            try:
                value = super()._field_construct_value(
                    value,
                    *args,
                    field_construct_kw={"format": format},
                )
            except PydanticCustomError:
                continue
            else:
                break
        else:
            raise PydanticCustomError(
                "time_format_not_allowed",
                f"{value!r} does not have the required time formats {formats}.",
            )
        return value


class _TimeFieldDeferred(DeferredValidationFieldMixin, Time):
    pass


TimeField = Annotated[_TimeFieldDeferred, TimeValidator()]
IsoTimeField = Annotated[
    _TimeFieldDeferred,
    TimeValidator(formats_allowed=["isot", "fits", "iso"]),
]
UnixTimeField = Annotated[
    _TimeFieldDeferred,
    TimeValidator(formats_allowed=("unix", "unix_tai")),
]


def time_field(formats_allowed=None):
    """Return a pydantic field type to valid time."""
    return Annotated[  # type: ignore[return-value]
        _TimeFieldDeferred,
        TimeValidator(formats_allowed=formats_allowed),
    ]


@dataclasses.dataclass
class QuantityValidator(_SimpleTypeValidatorMixin):
    """The constraints for validating `astropy.units.Quantity`."""

    physical_types_allowed: None | str | Sequence[str] = None

    _field_type: ClassVar = Quantity
    _field_type_name: ClassVar = "Quantity"
    _field_type_error_message: ClassVar = (
        "Quantiy, number, or string is required, got {type}."
    )
    _field_value_types: ClassVar = {numbers.Number, str}

    @cached_property
    def _field_physical_types(self):
        pts = self.physical_types_allowed
        if not pts:
            return None
        if isinstance(pts, str):
            return (pts,)
        return pts

    @cached_property
    def _field_value_schema_stub(self):
        schema: dict[str, Any] = {
            "type": "string",
            "format": "quantity",
        }
        pts = self._field_physical_types
        if pts is None:
            return schema
        schema["physical_types_allowed"] = pts
        return schema

    @cached_property
    def _field_value_error_message(self):
        if self._field_physical_types is None:
            return "Invalid quantity: {value}"
        return (
            "{value} is not a valid quantity of physical types"
            f" {self._field_physical_types}."
        )

    def _field_validate_value(self, value, *_args, **_kwargs):
        """Validate `astropy.units.Quantity`."""
        pts = self._field_physical_types
        if not pts:
            return value
        # check physical types
        if value.unit is None or value.unit.physical_type not in pts:
            raise PydanticCustomError(
                "invalid_quantity_phyical_type",
                f"{value!r} does not have the required physical types {pts}.",
            )
        return value


class _QuantityFieldDeferred(DeferredValidationFieldMixin, Quantity):
    pass


QuantityField = Annotated[_QuantityFieldDeferred, QuantityValidator()]
LengthQuantityField = Annotated[
    _QuantityFieldDeferred,
    QuantityValidator("length"),
]
AngleQuantityField = Annotated[
    _QuantityFieldDeferred,
    QuantityValidator("angler"),
]
TimeQuantityField = Annotated[
    _QuantityFieldDeferred,
    QuantityValidator("time"),
]
DimensionlessQuantityField = Annotated[
    _QuantityFieldDeferred,
    QuantityValidator("dimensionless"),
]


def quantity_field(physical_types_allowed=None):
    """Return a pydantic field type to valid quantity."""
    return Annotated[  # type: ignore[return-value]
        _QuantityFieldDeferred,
        QuantityValidator(physical_types_allowed=physical_types_allowed),
    ]


@dataclasses.dataclass
class PathType:
    """A better path-like pydantic field."""

    path_type: None | Literal["file", "dir", "new"]
    exists: bool = True
    resolve: bool = True

    def __post_init__(self):
        path_type = self.path_type
        if path_type == "new":
            self.exists = False
        if path_type is not None:
            # the native pydantic path type
            self._super = _PathType(path_type)
        else:
            self._super = None

    def __hash__(self):
        return (self.path_type, self.exists, self.resolve).__hash__()

    def __pydantic_modify_json_schema__(
        self,
        field_schema: dict[str, Any],
    ) -> dict[str, Any]:
        if self._super is not None:
            return self._super.__pydantic_modify_json_schema__(field_schema)
        field_schema.update(
            {"type": "string", "format": "path"},
        )
        return field_schema

    def __get_pydantic_core_schema__(
        self,
        schema: core_schema.CoreSchema,
        **kwargs,
    ) -> (
        core_schema.BeforeValidatorFunctionSchema
        | core_schema.AfterValidatorFunctionSchema
    ):
        # handle rootpath if present in the context
        # this has to go before any other validation
        schema0 = core_schema.general_before_validator_function(
            self.validate_rootpath,
            schema=schema,
        )
        # resolve if requested
        if self.resolve:
            schema1 = core_schema.general_after_validator_function(
                self.resolve_path,
                schema=schema0,
            )
        else:
            schema1 = schema0
        # check exists
        if self.exists:
            schema2 = core_schema.general_after_validator_function(
                self.validate_exists,
                schema=schema1,
            )
        else:
            schema2 = schema1
        # finally, do the type check if requested
        if self._super is not None:
            # in case the path_type is file, dir or new, the exists state is check
            # in the _super object
            return self._super.__get_pydantic_core_schema__(
                schema=schema2,
                kwargs=kwargs,
            )
        # nothing to do
        return schema2

    def validate_exists(self, path: Path, _info: ValidationInfo):
        """Ensure `path` exists."""
        if path.exists():
            return path
        raise PydanticCustomError("path_does_not_exist", "Path does not exist.")

    def validate_rootpath(self, path: Path, info: ValidationInfo):
        """Handle rootpath from context."""
        if info.context is not None:
            rootpath = info.context.get("rootpath", None)
        else:
            rootpath = None
        if rootpath is not None:
            return Path(rootpath).joinpath(path)
        return path

    def resolve_path(self, path: Path, _info: ValidationInfo):
        """Resolve the path."""
        return path.expanduser().resolve()


AnyPath = Annotated[Path, PathType(path_type=None, exists=False, resolve=False)]
AbsDirectoryPath = Annotated[Path, PathType(path_type="dir", exists=True, resolve=True)]
AbsFilePath = Annotated[Path, PathType(path_type="file", exists=True, resolve=True)]
AbsAnyPath = Annotated[Path, PathType(path_type=None, exists=False, resolve=True)]


class ModelListMeta(type(ImmutableBaseModel)):
    """A meta class to setup root models."""

    def __new__(cls, name, bases, namespace, **kwargs):  # noqa: D102
        @root_validator(pre=True)
        @classmethod
        def populate_root(mcls, values):  # noqa: ARG001
            return {"root_field": values}

        @model_serializer(mode="wrap")  # type: ignore
        def _serialize(self, handler, _info):
            data = handler(self)
            return data["root_field"]

        @classmethod
        def model_modify_json_schema(mcls, json_schema):  # noqa: ARG001
            return json_schema["properties"]["root_field"]

        namespace["populate_root"] = populate_root
        namespace["_serialize"] = _serialize
        namespace["model_modify_json_schema"] = model_modify_json_schema

        return super().__new__(cls, name, bases, namespace, **kwargs)


class ModelListBase(ImmutableBaseModel):
    """A base class for mode list."""

    root_field: Any

    def __iter__(self):
        return iter(self.root_field)

    def __getitem__(self, item):
        return self.root_field[item]


def create_list_model(name, item_model_cls):
    """Return a pydantic model to validate a list."""
    return cast(
        type[ModelListBase],
        ModelListMeta(
            name,
            (ModelListBase,),
            {
                "__annotations__": {
                    "root_field": list[item_model_cls],
                },
            },
        ),
    )
