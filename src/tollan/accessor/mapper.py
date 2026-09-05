"""Base mapper class for resolving flat schemas and accessing data."""

from __future__ import annotations

from dataclasses import fields
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

if TYPE_CHECKING:
    from collections.abc import Mapping as MappingABC

from ..utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)
from .schema import (
    MISSING,
    MappedField,
    MappedFieldSource,
    Mapping,
    MappingContext,
    Schema,
)

__all__ = [
    "Mapper",
]


class Mapper[SchemaT: Schema]:
    """Resolve schema fields and provide data access interface.

    Mapper resolves schema field mappings against a data source and retains
    the resulting physical names and explicitly requested resolution values.
    The data source is passed to read methods rather than stored as instance
    state, allowing mapper reuse across multiple datasets.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (auto-instantiated as class variable)
    """

    # Set on concrete subclasses by __init_subclass__; runtime type: SchemaT.
    schema: ClassVar

    # Schema instances cache (shared across all Mapper classes)
    _schema_instances: ClassVar[dict[type[Schema], Schema]] = {}

    _mapped_fields: dict[Mapping, MappedField]
    _mapped_fields_view: MappingABC[Mapping, MappedField]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Instantiate the schema from the resolved origin type variable."""
        super().__init_subclass__(**kwargs)

        bindings = resolve_concrete_generic_bindings(
            cls,
            Mapper,
            SchemaT=GenericBindingRequirement("schema", Schema),
        )
        if bindings is None:
            return
        schema_cls = bindings["SchemaT"]
        if schema_cls not in cls._schema_instances:
            cls._schema_instances[schema_cls] = schema_cls()
        cls.schema = cls._schema_instances[schema_cls]

    def __init__(
        self,
        mapped_fields: MappingABC[Mapping, MappedField] | None = None,
    ) -> None:
        """Initialize the mapper's private resolution state."""
        self._mapped_fields = dict(mapped_fields or {})
        self._mapped_fields_view = MappingProxyType(self._mapped_fields)

    @property
    def mapped_fields(self) -> MappingABC[Mapping, MappedField]:
        """Read-only view of the concrete mapping plan."""
        return self._mapped_fields_view

    @classmethod
    def from_data_source(
        cls,
        data_source: Any,
        defaults: dict[Mapping, Any] | None = None,
    ) -> Self:
        """Create mapper resolved against data source.

        Parameters
        ----------
        data_source : Any
            Data source to resolve against (xarray.Dataset, pd.DataFrame, etc.)
        defaults : dict[Mapping, Any] | None
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
        defaults: dict[Mapping, Any] | None = None,
    ) -> Self:
        """Create mapper resolved using only default values.

        Parameters
        ----------
        defaults : dict[Mapping, Any] | None
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
        defaults: dict[Mapping, Any],
    ) -> None:
        """Resolve each field in a flat schema in declaration order.

        Parameters
        ----------
        data_source : Any
            Data source to check for field existence and read values
        defaults : dict[Mapping, Any]
            Default values for fields not found in data source
        """
        schema = cast("SchemaT", type(self).schema)
        context = MappingContext(
            data_source=data_source,
            schema=schema,
            mapped_fields=self.mapped_fields,
        )

        # Earlier fields are visible to later conditional mappings.
        for schema_field in fields(schema):
            field_name = schema_field.name
            mapping = getattr(schema, field_name)
            if not isinstance(mapping, Mapping):
                continue

            # Build schema path using schema's get_schema_path method
            schema_path = schema.get_schema_path(field_name)

            # Get default value for this mapping (or MISSING sentinel)
            default_value = defaults.get(mapping, MISSING)

            self._mapped_fields[mapping] = self._resolve_mapping(
                data_source=data_source,
                mapping=mapping,
                default_value=default_value,
                schema_path=schema_path,
                context=context,
            )

    def _resolve_mapping(
        self,
        data_source: Any,
        mapping: Mapping,
        default_value: Any,
        context: MappingContext,
        schema_path: str = "",
    ) -> MappedField:
        """Resolve a single field mapping.

        Calls ``mapping.resolve(context)`` to handle conditional mappings.

        Parameters
        ----------
        data_source : Any
            Data source to check for field existence and read values
        mapping : Mapping
            Mapping to resolve (may be conditional)
        default_value : Any
            Default value if field not found in data source
        context : MappingContext
            Short-lived source and resolution state for custom mappings.
        schema_path : str
            Schema path for error messages

        Returns
        -------
        MappedField
            Concrete resolution state for the semantic field.
        """
        mapping_resolved = mapping.resolve(context)

        # Try to resolve from data_source first
        if data_source is not None:
            for name in mapping_resolved.names:
                if self._has_field(data_source, name):
                    # Only read value immediately if resolve_value is True
                    value = (
                        self._read_value(data_source, name)
                        if mapping_resolved.resolve_value
                        else MISSING
                    )
                    return MappedField(
                        mapping=mapping,
                        mapping_resolved=mapping_resolved,
                        name=name,
                        value=value,
                        source=MappedFieldSource.DATA_SOURCE,
                        schema_path=schema_path,
                    )

        # Not found in data_source, try default_value
        if default_value is not MISSING:
            return MappedField(
                mapping=mapping,
                mapping_resolved=mapping_resolved,
                name=mapping_resolved.names[0],
                value=default_value,
                source=MappedFieldSource.DEFAULT,
                schema_path=schema_path,
            )

        # No candidate found and no default value - return MISSING
        return MappedField(
            mapping=mapping,
            mapping_resolved=mapping_resolved,
            name=mapping_resolved.names[0],
            value=MISSING,
            source=MappedFieldSource.MISSING,
            schema_path=schema_path,
        )

    def __contains__(self, mapping: Mapping) -> bool:
        """Check if field exists in data source (enables `mapping in mapper`).

        Parameters
        ----------
        mapping : Mapping
            Schema field reference (e.g., schema.temp)

        Returns
        -------
        bool
            True if field exists in data source
        """
        resolved = self.mapped_fields.get(mapping)
        return resolved.source == MappedFieldSource.DATA_SOURCE if resolved else False

    def get_name(self, mapping: Mapping) -> str | None:
        """Get resolved physical field name.

        For fields resolved from a data source, returns the actual field name found.
        For fields with default values or missing fields, returns the first name
        from the mapping's name list (already set in resolved.name by _resolve_mapping).

        Parameters
        ----------
        mapping : Mapping
            Schema field reference

        Returns
        -------
        str | None
            Physical field name, or None if mapping not resolved
        """
        resolved = self.mapped_fields.get(mapping)
        return resolved.name if resolved else None

    def get_value(self, data_source: Any, mapping: Mapping) -> Any:
        """Read a field value from the supplied data source.

        Values captured during mapping resolution remain available in
        ``mapped_fields`` as part of the concrete mapper, but do not replace a
        read from ``data_source``. Only mapper defaults are returned without
        consulting the source.

        Parameters
        ----------
        data_source : Any
            Data source to read from
        mapping : Mapping
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

        # For DATA_SOURCE, always read the explicitly supplied source. The
        # resolved value may be a discriminator captured by resolve_value=True
        # and belongs to the concrete mapper rather than this read operation.
        return self._read_value(data_source, resolved.name)

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
