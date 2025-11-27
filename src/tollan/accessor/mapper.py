"""Base mapper class for navigating schema trees and accessing data."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, ClassVar

from ..utils.typing import get_typing_args
from .schema import MISSING, MappedField, MappedFieldSource, MappingBase, Schema

__all__ = [
    "Mapper",
]


@dataclass
class Mapper[SchemaT: Schema]:
    """Resolve schema fields and provide data access interface.

    Mapper resolves a schema's field mappings against a data source,
    storing the resolved physical field names and optionally loading values.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (auto-instantiated as class variable)
    """

    # Schema instance (auto-instantiated and cached via __init_subclass__)
    schema: ClassVar[SchemaT]  # type: ignore[assignment]

    # Schema instances cache (shared across all Mapper classes)
    _schema_instances: ClassVar[dict[type[SchemaT], SchemaT]] = {}  # type: ignore[assignment]

    # Dataclass fields
    data_source: Any = None
    """Data source to resolve against (xarray.Dataset, pd.DataFrame, etc.)"""

    default_values: dict[MappingBase, Any] = field(default_factory=dict)
    """Default values for schema fields (mapping -> value).

    Used as fallback when data_source doesn't have a field.
    """
    mapped_fields: dict[MappingBase, MappedField] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-instantiate schema from generic parameter."""
        super().__init_subclass__(**kwargs)

        # Try to extract schema class from Mapper[SchemaT] generic parameter
        # This will only succeed for concrete instantiations like XarrayMapper[MySchema]
        # For generic bases like DataFrameMapper[SchemaT],
        # this will find no concrete schemas
        schema_classes = get_typing_args(
            cls,
            max_depth=2,
            bound=Schema,
            unique=False,
        )

        if len(schema_classes) > 1:
            msg = (
                f"Multiple schema classes found for {cls.__name__}: "
                f"{schema_classes}. Cannot auto-instantiate."
            )
            raise TypeError(msg)
        # If we found exactly one schema class, instantiate it (with caching)
        if len(schema_classes) == 1:
            schema_cls = schema_classes[0]
            if schema_cls not in cls._schema_instances:
                cls._schema_instances[schema_cls] = schema_cls()
            cls.schema = cls._schema_instances[schema_cls]

    def __post_init__(self) -> None:
        """Populate mapped fields after dataclass initialization.

        Raises
        ------
        ValueError
            If neither data_source nor default_values are provided.
        """
        if self.data_source is None and self.default_values is None:
            msg = "At least one of data_source or default_values must be provided"
            raise ValueError(msg)

        # Populate mapped fields from schema
        self._populate_from_schema()

    def _populate_from_schema(self) -> None:
        """Populate mapped_fields dict from schema in depth-first order.

        Updates self.mapped_fields in place by traversing schema fields
        and resolving each mapping against data_source and/or default_values.
        """
        # Traverse schema fields in insertion order (depth-first)
        for schema_field in fields(self.schema):
            field_name = schema_field.name
            mapping = getattr(self.schema, field_name)
            if not isinstance(mapping, MappingBase):
                continue

            # Build schema path using schema's get_schema_path method
            schema_path = self.schema.get_schema_path(field_name)

            # Get default value for this mapping (or MISSING sentinel)
            default_value = self.default_values.get(mapping, MISSING)

            # Resolve this field mapping
            resolved_field = self._resolve_field_mapping(
                mapping=mapping,
                default_value=default_value,
                schema_path=schema_path,
            )

            if resolved_field:
                self.mapped_fields[mapping] = resolved_field

    def _resolve_field_mapping(
        self,
        mapping: MappingBase,
        default_value: Any,
        schema_path: str = "",
    ) -> MappedField | None:
        """Resolve a field mapping from data_source and/or default_value.

        Parameters
        ----------
        mapping : MappingBase
            Mapping to resolve
        default_value : Any
            Default value to use if not found in data_source (can be MISSING sentinel)
        schema_path : str, optional
            Dot-separated path in schema (e.g., "MySchema.field")

        Returns
        -------
        MappedField | None
            Resolved field or None if not found
        """
        # Get the FieldMapping from the MappingBase
        # Pass self (mapper) so resolve() can access data_source, mapped_fields, etc.
        field_mapping = mapping.resolve(self)

        # Try to resolve from data_source first
        if self.data_source is not None:
            for name in field_mapping.names:
                if self._has_field(name):
                    # Only read value immediately if resolve_value is True
                    value = (
                        self._read_value(name)
                        if field_mapping.resolve_value
                        else MISSING
                    )
                    return MappedField(
                        field_mapping=field_mapping,
                        name=name,
                        value=value,
                        source=MappedFieldSource.DATA_SOURCE,
                        schema_path=schema_path,
                    )

        # Not found in data_source, try default_value
        if default_value is not MISSING:
            return MappedField(
                field_mapping=field_mapping,
                name="",
                value=default_value,
                source=MappedFieldSource.DEFAULT,
                schema_path=schema_path,
            )

        # No candidate found and no default value
        if field_mapping.required:
            msg = f"Required field not found (tried: {field_mapping.names})"
            raise KeyError(msg)

        return MappedField(
            field_mapping=field_mapping,
            name="",
            value=MISSING,
            source=MappedFieldSource.MISSING,
            schema_path=schema_path,
        )

    def has(self, mapping: MappingBase) -> bool:
        """Check if field exists in data source.

        Parameters
        ----------
        mapping : MappingBase
            Schema field reference (e.g., schema.temp)

        Returns
        -------
        bool
            True if field exists
        """
        resolved = self.mapped_fields.get(mapping)
        return resolved.source == MappedFieldSource.DATA_SOURCE if resolved else False

    def get_name(self, mapping: MappingBase) -> str | None:
        """Get resolved physical field name.

        Parameters
        ----------
        mapping : MappingBase
            Schema field reference

        Returns
        -------
        str | None
            Physical field name, or None if not found
        """
        resolved = self.mapped_fields.get(mapping)
        return (
            resolved.name
            if resolved and resolved.source == MappedFieldSource.DATA_SOURCE
            else None
        )

    def get_value(self, mapping: MappingBase) -> Any:
        """Get field value (loads if not already loaded).

        Parameters
        ----------
        mapping : MappingBase
            Schema field reference

        Returns
        -------
        Any
            Field value

        Raises
        ------
        KeyError
            If field not found
        """
        resolved = self.mapped_fields.get(mapping)

        if not resolved or resolved.source == MappedFieldSource.MISSING:
            msg = f"Field not found: {mapping}"
            raise KeyError(msg)

        # For DEFAULT source, value is already set
        if resolved.source == MappedFieldSource.DEFAULT:
            return resolved.value

        # For DATA_SOURCE, load on demand if not already loaded
        if resolved.value is MISSING:
            resolved.value = self._read_value(resolved.name)

        return resolved.value

    def __getitem__(self, mapping: MappingBase) -> Any:
        """Get value using convenience syntax: mapper[schema.temp]."""
        return self.get_value(mapping)

    def _has_field(self, name: str) -> bool:
        """Check if physical field exists in data source.

        Subclasses must implement.
        """
        msg = f"{self.__class__.__name__} must implement _has_field()"
        raise NotImplementedError(msg)

    def _read_value(self, name: str) -> Any:
        """Read physical field value from data source.

        Subclasses must implement.
        """
        msg = f"{self.__class__.__name__} must implement _read_value()"
        raise NotImplementedError(msg)
