import dataclasses
import numbers
from collections.abc import Iterator, Sequence
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Callable, ClassVar, Generic, Literal, TypeVar

from astropy.time import Time
from astropy.units import Quantity
from pydantic import BaseModel, ConfigDict, RootModel, ValidationInfo
from pydantic.annotated import GetCoreSchemaHandler
from pydantic.json_schema import GenerateJsonSchema as _GenerateJsonSchema
from pydantic.json_schema import (
    GetJsonSchemaHandler,
    JsonSchemaValue,
    update_json_schema,
)
from pydantic.types import PathType as _PathType
from pydantic_core import CoreSchema, core_schema

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
    "GenerateJsonSchema",
]


class GenerateJsonSchema(_GenerateJsonSchema):
    """Custom json schema generator."""

    _default_serializers: dict[type[Any], Callable] = {}

    @classmethod
    def register_default_serializers(cls, dft_type: type[Any], handler: Callable):
        """Add handler for type."""
        cls._default_serializers[dft_type] = handler

    def encode_default(self, dft: Any) -> Any:
        """Override default behavior to inovke the the custom type handlers."""
        for dft_type, handler in self._default_serializers.items():
            if isinstance(dft, dft_type):
                dft = handler(dft)
                break
        return super().encode_default(dft)


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

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        """Dump model json schema."""
        kwargs.setdefault("schema_generator", GenerateJsonSchema)
        return super().model_json_schema(*args, **kwargs)


class _SimpleTypeValidatorMixin:
    """A mixin class for simple custom type validation."""

    _field_type: ClassVar[type]
    _field_type_name: ClassVar[str]
    _field_type_error_message: ClassVar[str]
    _field_value_types: ClassVar[set]

    _field_value_schema_stub: dict[str, Any]
    _field_value_error_message: str

    def __init_subclass__(cls):
        if cls._field_type not in cls._field_value_types:
            cls._field_value_types.add(cls._field_type)

    def __get_pydantic_json_schema__(
        self,
        _schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        js = handler(core_schema.str_schema())
        update_json_schema(js, self._field_value_schema_stub)
        return js

    def __get_pydantic_core_schema__(
        self,
        _source: type[Any],
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.general_plain_validator_function(
            self._field_validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                self._field_serialize,
                info_arg=False,
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
            raise TypeError(
                self._field_type_error_message.format(type=type(value)),
            )
        return value

    def _field_construct_value(self, value, *_args, **kwargs):
        try:
            field_construct_kw = kwargs.get("field_construct_kw", {})
            return self._field_type(value, **field_construct_kw)
        except ValueError as e:
            raise ValueError(
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
            except ValueError:
                continue
            else:
                break
        else:
            raise ValueError(
                f"{value!r} does not have the required time formats {formats}.",
            )
        return value


TimeField = Annotated[Time, TimeValidator()]
IsoTimeField = Annotated[
    Time,
    TimeValidator(formats_allowed=["isot", "fits", "iso"]),
]
UnixTimeField = Annotated[
    Time,
    TimeValidator(formats_allowed=("unix", "unix_tai")),
]


def time_field(formats_allowed=None):
    """Return a pydantic field type to valid time."""
    return Annotated[  # type: ignore[return-value]
        Time,
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
            raise ValueError(
                f"{value!r} does not have the required physical types {pts}.",
            )
        return value


QuantityField = Annotated[Quantity, QuantityValidator()]
LengthQuantityField = Annotated[
    Quantity,
    QuantityValidator("length"),
]
AngleQuantityField = Annotated[
    Quantity,
    QuantityValidator("angler"),
]
TimeQuantityField = Annotated[
    Quantity,
    QuantityValidator("time"),
]
DimensionlessQuantityField = Annotated[
    Quantity,
    QuantityValidator("dimensionless"),
]


def quantity_field(physical_types_allowed=None):
    """Return a pydantic field type to valid quantity."""
    return Annotated[  # type: ignore[return-value]
        Quantity,
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

    def __get_pydantic_json_schema__(
        self,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        if self._super is not None:
            return self._super.__get_pydantic_json_schema__(core_schema, handler)
        js = handler(core_schema)
        js.update(
            {"type": "string", "format": "path"},
        )
        return js

    def __get_pydantic_core_schema__(
        self,
        source: type[Any],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        # handle rootpath if present in the context
        schema0 = core_schema.general_before_validator_function(
            self.validate_path_rootpath,
            schema=handler(source),
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
            return core_schema.chain_schema(
                [
                    schema2,
                    self._super.__get_pydantic_core_schema__(
                        source=source,
                        handler=handler,
                    ),
                ],
            )
        # nothing to do
        return schema2

    def validate_exists(self, path: Path, _info: ValidationInfo):
        """Ensure `path` exists."""
        if path.exists():
            return path
        raise ValueError(f"Path {path} does not exist.")

    def validate_path_rootpath(self, path: str | Path, info: ValidationInfo):
        """Handle rootpath from context."""
        if info.context is not None:
            rootpath = info.context.get("rootpath", None)
        else:
            rootpath = None
        if rootpath is not None:
            return Path(rootpath).joinpath(path)
        return Path(path)

    def resolve_path(self, path: Path, _info: ValidationInfo):
        """Resolve the path."""
        return path.expanduser().resolve()


AnyPath = Annotated[Path, PathType(path_type=None, exists=False, resolve=False)]
AbsDirectoryPath = Annotated[Path, PathType(path_type="dir", exists=True, resolve=True)]
AbsFilePath = Annotated[Path, PathType(path_type="file", exists=True, resolve=True)]
AbsAnyPath = Annotated[Path, PathType(path_type=None, exists=False, resolve=True)]


ModelListItemType = TypeVar("ModelListItemType")


class ModelListBase(
    ImmutableBaseModel,
    RootModel[list[ModelListItemType]],
    Generic[ModelListItemType],
):
    """A base class for model list."""

    def __iter__(self) -> Iterator[ModelListItemType]:
        return iter(self.root)

    def __getitem__(self, item: int) -> ModelListItemType:
        return self.root[item]


def _to_str_serializer(v):
    return str(v)


GenerateJsonSchema.register_default_serializers(Time, _to_str_serializer)
GenerateJsonSchema.register_default_serializers(Quantity, _to_str_serializer)
