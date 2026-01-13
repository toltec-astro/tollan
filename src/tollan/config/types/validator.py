"""Validator mixin for creating custom Pydantic field validators.

This module provides a reusable mixin pattern for implementing custom
Pydantic field validators that follow a three-step validation pipeline:
1. Type validation - ensure input is acceptable type
2. Construction - build target object from input
3. Value validation - validate constructed object

The mixin is used by astronomy-specific validators like QuantityValidator,
TimeValidator, and SkyCoordValidator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic_core import core_schema

__all__ = ["_SimpleTypeValidatorMixin"]

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
    from pydantic.json_schema import JsonSchemaValue


class _SimpleTypeValidatorMixin[FieldT]:
    """Mixin for creating custom Pydantic field validators.

    This mixin provides a standardized three-step validation pipeline
    for custom types. Subclasses define the target type and customize
    validation behavior by overriding methods and properties.

    Class Attributes to Define
    ---------------------------
    _field_type : ClassVar[type]
        The target type to validate and construct
    _field_type_name : ClassVar[str]
        Human-readable name for the type
    _field_type_error_message : ClassVar[str]
        Error message template for type errors
    _field_value_types : ClassVar[set]
        Set of acceptable input types
    _field_value_json_schema_stub : dict
        JSON schema stub for this type
    _field_value_error_message : str
        Error message for value validation failures

    Methods to Override
    -------------------
    _field_serialize(value) : Any
        Serialize the validated value
    _field_validate_type(value, info) : Any
        Validate input type before construction
    _field_construct_value(value, info) : Any
        Construct the target type from input
    _field_validate_value(value, info) : Any
        Validate the constructed object
    """

    _field_type: ClassVar[type]
    _field_type_name: ClassVar[str]
    _field_type_error_message: ClassVar[str]
    _field_value_types: ClassVar[set]
    _field_value_json_schema_stub: dict[str, Any]
    _field_value_error_message: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls._field_type not in cls._field_value_types:
            cls._field_value_types.add(cls._field_type)

    def __get_pydantic_json_schema__(
        self,
        schema: core_schema.CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        js = handler(core_schema.str_schema())
        js.update(self._field_value_json_schema_stub)
        return js

    def __get_pydantic_core_schema__(
        self,
        source: type[Any],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.with_info_plain_validator_function(
            self._field_validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                self._field_serialize,
                info_arg=False,
            ),
        )

    def _field_serialize(self, value: FieldT) -> str:
        return str(value)

    def _field_validate(self, value: Any, info: core_schema.ValidationInfo) -> FieldT:
        # 1. validate type first
        value = self._field_validate_type(value, info)
        # 2. do construction
        value = self._field_construct_value(value, info)
        # 3. do post check
        return self._field_validate_value(value, info)

    def _field_validate_type[T](self, value: T, *args, **kwargs) -> T:
        if not isinstance(value, tuple(self._field_value_types)):
            raise TypeError(
                self._field_type_error_message.format(type=type(value)),
            )
        return value

    def _field_construct_value(self, value: Any, *args, **kwargs) -> FieldT:
        try:
            field_construct_kw = kwargs.get("field_construct_kw", {})
            return self._field_type(value, **field_construct_kw)
        except ValueError as e:
            raise ValueError(
                self._field_value_error_message.format(value=value),
            ) from e

    def _field_validate_value(self, value: FieldT, *args, **kwargs) -> FieldT:
        # we require the value has scalar semantics for array-like types
        if not hasattr(value, "shape"):
            return value
        shape = value.shape  # pyright: ignore[reportAttributeAccessIssue]
        if shape != ():
            msg = f"{self._field_type_name} value must be a scalar, got {shape}"
            raise ValueError(msg)
        return value
