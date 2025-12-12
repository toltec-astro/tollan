"""Base mapper class for navigating schema trees and accessing data."""

from __future__ import annotations

from dataclasses import fields
from typing import Any, ClassVar, Self

from ..utils.typing import get_typing_args
from .schema import MISSING, MappedField, MappedFieldSource, MappingBase, Schema

__all__ = [
    "Mapper",
]


class Mapper[SchemaT: Schema]:
    """Resolve schema fields and provide data access interface.

    Mapper resolves schema field mappings against a data source and caches
    the results. The data source is passed as a parameter to methods rather
    than stored as instance state, allowing mapper reuse across multiple
    datasets.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (auto-instantiated as class variable)
    """

    # Schema instance (auto-instantiated and cached via __init_subclass__)
    schema: ClassVar[SchemaT]  # type: ignore[assignment]

    # Schema instances cache (shared across all Mapper classes)
    _schema_instances: ClassVar[dict[type[SchemaT], SchemaT]] = {}  # type: ignore[assignment]

    _mapped_fields: dict[MappingBase, MappedField]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-instantiate schema from generic parameter."""
        super().__init_subclass__(**kwargs)

        # Get schema class - returns None for generic base classes with TypeVars,
        # or raises ValueError for concrete classes missing a schema
        schema_cls = get_typing_args(
            cls,
            max_depth=2,
            bound=Schema,
            unique=True,
        )

        # Only set schema for concrete classes (generic base classes get None)
        if schema_cls is not None:
            if schema_cls not in cls._schema_instances:
                cls._schema_instances[schema_cls] = schema_cls()
            cls.schema = cls._schema_instances[schema_cls]

    def __init__(
        self,
        mapped_fields: dict[MappingBase, MappedField] | None = None,
    ) -> None:
        """Initialize mapper with empty mapped_fields cache."""
        self._mapped_fields: dict[MappingBase, MappedField] = mapped_fields or {}

    @property
    def mapped_fields(self) -> dict[MappingBase, MappedField]:
        """Resolved mapped fields cache."""
        return self._mapped_fields

    @classmethod
    def from_data_source(
        cls,
        data_source: Any,
        defaults: dict[MappingBase, Any] | None = None,
    ) -> Self:
        """Create mapper resolved against data source.

        Parameters
        ----------
        data_source : Any
            Data source to resolve against (xarray.Dataset, pd.DataFrame, etc.)
        defaults : dict[MappingBase, Any] | None
            Default values for fields not found in data_source

        Returns
        -------
        Self
            Mapper with resolved field mappings
        """
        mapper = cls()
        mapper._populate_from_schema(data_source, defaults or {})
        return mapper

    @classmethod
    def from_defaults(
        cls,
        defaults: dict[MappingBase, Any] | None = None,
    ) -> Self:
        """Create mapper resolved using only default values.

        Parameters
        ----------
        defaults : dict[MappingBase, Any] | None
            Default values for fields

        Returns
        -------
        Self
            Mapper with resolved field mappings
        """
        return cls.from_data_source(
            data_source=None,
            defaults=defaults,
        )

    def _populate_from_schema(
        self,
        data_source: Any,
        defaults: dict[MappingBase, Any],
    ) -> None:
        """Traverse schema and resolve all field mappings.

        Parameters
        ----------
        data_source : Any
            Data source to check for field existence and read values
        defaults : dict[MappingBase, Any]
            Default values for fields not found in data source
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
            default_value = defaults.get(mapping, MISSING)

            # Resolve this field mapping
            resolved_field = self._resolve_mapping(
                data_source=data_source,
                mapping=mapping,
                default_value=default_value,
                schema_path=schema_path,
            )

            if resolved_field:
                self.mapped_fields[mapping] = resolved_field

    def _resolve_mapping(
        self,
        data_source: Any,
        mapping: MappingBase,
        default_value: Any,
        schema_path: str = "",
    ) -> MappedField | None:
        """Resolve a single field mapping.

        Calls mapping.resolve(self) to handle conditional mappings, which
        can check previously resolved fields in self.mapped_fields.

        Parameters
        ----------
        data_source : Any
            Data source to check for field existence and read values
        mapping : MappingBase
            Mapping to resolve (may be conditional)
        default_value : Any
            Default value if field not found in data source
        schema_path : str
            Schema path for error messages

        Returns
        -------
        MappedField | None
            Resolved field or None if optional and not found
        """
        # Get the FieldMapping from the MappingBase
        # Pass self (mapper) so resolve() can access mapped_fields
        # for conditional resolution based on previously resolved fields
        mapping = mapping.resolve(self)

        # Try to resolve from data_source first
        if data_source is not None:
            for name in mapping.names:
                if self._has_field(data_source, name):
                    # Only read value immediately if resolve_value is True
                    value = (
                        self._read_value(data_source, name)
                        if mapping.resolve_value
                        else MISSING
                    )
                    return MappedField(
                        mapping=mapping,
                        name=name,
                        value=value,
                        source=MappedFieldSource.DATA_SOURCE,
                        schema_path=schema_path,
                    )

        # Not found in data_source, try default_value
        if default_value is not MISSING:
            return MappedField(
                mapping=mapping,
                name=mapping.names[0],
                value=default_value,
                source=MappedFieldSource.DEFAULT,
                schema_path=schema_path,
            )

        # No candidate found and no default value - return MISSING
        return MappedField(
            mapping=mapping,
            name=mapping.names[0],
            value=MISSING,
            source=MappedFieldSource.MISSING,
            schema_path=schema_path,
        )

    def __contains__(self, mapping: MappingBase) -> bool:
        """Check if field exists in data source (enables `mapping in mapper`).

        Parameters
        ----------
        mapping : MappingBase
            Schema field reference (e.g., schema.temp)

        Returns
        -------
        bool
            True if field exists in data source
        """
        resolved = self.mapped_fields.get(mapping)
        return resolved.source == MappedFieldSource.DATA_SOURCE if resolved else False

    def has(self, mapping: MappingBase) -> bool:
        """Check if field exists in data source.

        This is a convenience method that delegates to `__contains__`.
        Prefer using the `in` operator: `mapping in mapper`.

        Parameters
        ----------
        mapping : MappingBase
            Schema field reference (e.g., schema.temp)

        Returns
        -------
        bool
            True if field exists in data source
        """
        return mapping in self

    def get_name(self, mapping: MappingBase) -> str | None:
        """Get resolved physical field name.

        For fields resolved from a data source, returns the actual field name found.
        For fields with default values or missing fields, returns the first name
        from the mapping's name list (already set in resolved.name by _resolve_mapping).

        Parameters
        ----------
        mapping : MappingBase
            Schema field reference

        Returns
        -------
        str | None
            Physical field name, or None if mapping not resolved
        """
        resolved = self.mapped_fields.get(mapping)
        return resolved.name if resolved else None

    def get_value(self, data_source: Any, mapping: MappingBase) -> Any:
        """Get field value, loading on demand if not already cached.

        Parameters
        ----------
        data_source : Any
            Data source to read from if value not cached
        mapping : MappingBase
            Schema field reference (e.g., schema.temp)

        Returns
        -------
        Any
            Field value

        Raises
        ------
        KeyError
            If field not found or is MISSING
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
            resolved.value = self._read_value(data_source, resolved.name)

        return resolved.value

    def _has_field(self, data_source: Any, name: str) -> bool:
        """Check if physical field exists in data source.

        Default implementation returns False (no fields exist).
        Subclasses should override this method for their data source type.

        Parameters
        ----------
        data_source : Any
            Data source to check (type depends on subclass)
        name : str
            Physical field name to check

        Returns
        -------
        bool
            True if field exists, False by default
        """
        return False

    def _read_value(self, data_source: Any, name: str) -> Any:
        """Read physical field value from data source.

        Default implementation returns None (no value available).
        Subclasses should override this method for their data source type.

        Parameters
        ----------
        data_source : Any
            Data source to read from (type depends on subclass)
        name : str
            Physical field name to read

        Returns
        -------
        Any
            Field value, None by default
        """
        return None
