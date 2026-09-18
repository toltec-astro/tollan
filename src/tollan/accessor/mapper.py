"""Base mapper class for resolving flat schemas and accessing data."""

from __future__ import annotations

from dataclasses import fields, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping as MappingABC

from ..utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
)
from .schema import (
    MISSING,
    FieldLocation,
    MappedField,
    MappedFieldSource,
    Mapping,
    MappingContext,
    NameMapping,
    Schema,
)

__all__ = [
    "Mapper",
]


class Mapper[SchemaT: Schema, DataSourceT = Any, VariableT = Any]:
    """Resolve schema fields and provide data access interface.

    Mapper resolves schema field mappings against a data source and retains
    the resulting physical names and explicitly requested resolution values.
    The data source is passed to read methods rather than stored as instance
    state, allowing mapper reuse across multiple datasets.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (auto-instantiated as class variable)
    DataSourceT
        Source type accepted by this mapper. Defaults to Any; storage-specific
        mapper classes supply their source type.
    VariableT
        Native variable type returned by get_var(). Defaults to Any.
    """

    # Set on concrete subclasses by __init_subclass__; runtime type: SchemaT.
    schema: ClassVar

    # Schema instances cache (shared across all Mapper classes)
    _schema_instances: ClassVar[dict[type[Schema], Schema]] = {}

    _supported_locations: ClassVar[tuple[FieldLocation, ...]] = (FieldLocation.var,)

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
        data_source: DataSourceT | None,
        defaults: dict[Mapping, Any] | None = None,
    ) -> Self:
        """Create mapper resolved against data source.

        Parameters
        ----------
        data_source : DataSourceT or None
            Data source to resolve against (xarray.Dataset, pd.DataFrame, etc.)
        defaults : dict[Mapping, Any] | None
            Fallbacks used by get_value_or_default() and eager resolution when
            the field is absent. Retained even when data_source has the field.

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
        data_source: DataSourceT | None,
        defaults: dict[Mapping, Any],
    ) -> None:
        """Resolve each field in a flat schema in declaration order.

        Parameters
        ----------
        data_source : DataSourceT or None
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
            value_default = defaults.get(mapping, MISSING)

            self._mapped_fields[mapping] = self._resolve_mapping(
                data_source=data_source,
                mapping=mapping,
                value_default=value_default,
                schema_path=schema_path,
                context=context,
            )

    def _resolve_mapping(
        self,
        data_source: DataSourceT | None,
        mapping: Mapping,
        value_default: Any,
        context: MappingContext,
        schema_path: str = "",
    ) -> MappedField:
        """Resolve a single field mapping.

        Calls ``mapping.resolve(context)`` to handle conditional mappings.

        Parameters
        ----------
        data_source : DataSourceT or None
            Data source to check for field existence and read values
        mapping : Mapping
            Mapping to resolve (may be conditional)
        value_default : Any
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
        mapped = None

        # Try to resolve from data_source first
        if data_source is not None:
            for candidate in mapping_resolved.candidates:
                location = self._resolve_location(
                    data_source, candidate.name, candidate.location
                )
                if location is not None:
                    mapped = MappedField(
                        mapping=mapping,
                        mapping_resolved=mapping_resolved,
                        name=candidate.name,
                        location=location,
                        value_default=value_default,
                        source=MappedFieldSource.DATA_SOURCE,
                        schema_path=schema_path,
                    )
                    break

        if mapped is None:
            candidate = mapping_resolved.candidates[0]
            mapped = MappedField(
                mapping=mapping,
                mapping_resolved=mapping_resolved,
                name=candidate.name,
                location=candidate.location,
                value_default=value_default,
                source=(
                    MappedFieldSource.DEFAULT
                    if value_default is not MISSING
                    else MappedFieldSource.MISSING
                ),
                schema_path=schema_path,
            )

        if (
            mapping_resolved.resolve_value
            and mapped.source != MappedFieldSource.MISSING
        ):
            mapped = replace(
                mapped, value=self._read_value_or_default(data_source, mapped)
            )
        return mapped

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

    def get_value(self, data_source: DataSourceT, mapping: Mapping) -> Any:
        """Read a field value from the supplied data source.

        Values captured during mapping resolution remain available in
        ``mapped_fields`` as part of the concrete mapper, but do not replace a
        read from ``data_source``. Configured defaults are not used; call
        ``get_value_or_default()`` to allow a fallback for an absent field.

        Parameters
        ----------
        data_source : DataSourceT
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
            If the mapping has no resolved location or the field is absent.
            Backend-specific lookup and read errors propagate unchanged.
        """
        resolved = self.mapped_fields.get(mapping)

        if resolved is None or resolved.location is None:
            msg = f"Field not found: {mapping}"
            raise KeyError(msg)

        return self._read_value(data_source, resolved.name, resolved.location)

    def get_value_or_default(
        self, data_source: DataSourceT | None, mapping: Mapping
    ) -> Any:
        """Read the mapped source value, or return its configured fallback.

        The fallback is used only when the field is absent at its recorded
        name and location, no location was resolved, or data_source is None.
        Present values, including None and zero, take precedence. Read errors
        propagate without using the fallback. Neither the fallback nor the
        source value is decoded or validated by this method.

        Parameters
        ----------
        data_source : DataSourceT or None
            Source to read, or None to use only the configured fallback.
        mapping : Mapping
            Schema field reference.

        Returns
        -------
        Any
            Source value or configured fallback, not a resolution snapshot.

        Raises
        ------
        KeyError
            If the mapping is unknown, or neither a source field nor a
            fallback is available.
        """
        mapped = self.mapped_fields[mapping]
        return self._read_value_or_default(data_source, mapped)

    def has_attr(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Return whether the mapped attribute exists in the supplied source."""
        mapped = self.mapped_fields.get(field)
        return (
            mapped is not None
            and mapped.location == FieldLocation.attr
            and self._has_attr(data_source, mapped.name)
        )

    def has_var(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Return whether the mapped variable exists in the supplied source."""
        mapped = self.mapped_fields.get(field)
        return (
            mapped is not None
            and mapped.location == FieldLocation.var
            and self._has_var(data_source, mapped.name)
        )

    def get_var(self, data_source: DataSourceT, field: Mapping) -> VariableT:
        """Return the native variable without requesting its values.

        Returns a DataArray for xarray, a Variable for netCDF4, or a Series for
        pandas. Labels, metadata, and the variable's backend remain available.
        Defaults do not substitute for a native variable.

        Raises
        ------
        ValueError
            If the mapping is absent or selects a non-variable location.
        KeyError
            If the variable does not exist in the supplied source.
        """
        mapped = self.mapped_fields.get(field)
        if mapped is None or mapped.location != FieldLocation.var:
            msg = (
                f"Field {self.get_name(field) or field!r} not found as a variable "
                f"in {type(data_source).__name__}"
            )
            raise ValueError(msg)
        return self._get_var(data_source, mapped.name)

    def get_scalar(self, data_source: DataSourceT, field: Mapping) -> Any:
        """Read an attribute, scalar variable, or dimension length.

        Attributes are returned unchanged. Variable reads use the backend's
        scalar rules: xarray and netCDF4 accept 0-D variables and single-element
        string variables; pandas columns are not scalars. Bytes remain bytes.
        Variable shape is checked before loading values. This method reads the
        supplied source, not defaults or captured resolution values.

        Raises
        ------
        ValueError
            If the mapping has no known location or the variable is not scalar.
        KeyError
            If the variable or dimension is absent from the supplied source.
        """
        mapped = self.mapped_fields.get(field)
        if mapped is None or mapped.location is None:
            msg = (
                f"Field {self.get_name(field) or field!r} "
                f"not found in {type(data_source).__name__}"
            )
            raise ValueError(msg)
        if mapped.location == FieldLocation.var:
            return self._read_scalar_var(self._get_var(data_source, mapped.name))
        return self._read_value(data_source, mapped.name, mapped.location)

    def get_str(
        self,
        data_source: DataSourceT,
        field: Mapping,
        *,
        encoding: str = "utf-8",
    ) -> str:
        """Read one string, decoding bytes and removing outer null/space padding.

        Accepts text attributes. For xarray and netCDF4, also accepts
        scalar or single-element string variables and one-dimensional character
        arrays (S1/U1). Pandas columns are not individual strings. Variable shape
        and dtype are checked before loading; object values are checked afterward.
        Defaults and captured resolution values do not replace a source read.

        Raises
        ------
        KeyError
            If the mapped field is missing.
        ValueError
            If the value does not represent one string.
        TypeError
            If a scalar value is not text.
        UnicodeDecodeError
            If bytes cannot be decoded using the requested encoding.
        """
        mapped = self.mapped_fields.get(field)
        if mapped is None or mapped.location is None:
            msg = f"Field not found: {field}"
            raise KeyError(msg)
        if mapped.location == FieldLocation.var:
            value = self._read_str_var(self._get_var(data_source, mapped.name))
        else:
            value = self._read_value(data_source, mapped.name, mapped.location)
        return _decode_str(value, name=mapped.name, encoding=encoding)

    def has_dim(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Return whether the mapped dimension exists in the supplied source."""
        mapped = self.mapped_fields.get(field)
        return (
            mapped is not None
            and mapped.location == FieldLocation.dim
            and self._has_dim(data_source, mapped.name)
        )

    def get_dim(self, data_source: DataSourceT, field: Mapping) -> int:
        """Read the current length of a mapped dimension without loading arrays.

        Parameters
        ----------
        data_source : DataSourceT
            Source whose dimension length is requested.
        field : Mapping
            Dimension mapping from the schema.

        Returns
        -------
        int
            Current dimension length, regardless of any captured resolution value.

        Raises
        ------
        KeyError
            If the mapping is absent, selects another location, or the dimension
            does not exist in the supplied source.
        """
        mapped = self.mapped_fields.get(field)
        if mapped is None or mapped.location != FieldLocation.dim:
            msg = f"Dimension not found: {field}"
            raise KeyError(msg)
        return self._get_dim(data_source, mapped.name)

    def _resolve_location(
        self, data_source: DataSourceT, name: str, location: FieldLocation | None
    ) -> FieldLocation | None:
        """Locate a candidate without reading values; reject ambiguous names."""
        if location is not None:
            if location not in self._supported_locations:
                msg = (
                    f"{type(self).__name__} does not support "
                    f"location {location.value!r}"
                )
                raise ValueError(msg)
            return location if self._has_field(data_source, name, location) else None
        matches = [
            candidate
            for candidate in self._supported_locations
            if self._has_field(data_source, name, candidate)
        ]
        if len(matches) > 1:
            locations = ", ".join(match.value for match in matches)
            msg = (
                f"Ambiguous field {name!r} in locations {locations}; specify a location"
            )
            raise ValueError(msg)
        return matches[0] if matches else None

    def _has_field(
        self, data_source: DataSourceT, name: str, location: FieldLocation
    ) -> bool:
        """Check a physical name at the specified location without reading values."""
        match location:
            case FieldLocation.attr:
                return self._has_attr(data_source, name)
            case FieldLocation.var:
                return self._has_var(data_source, name)
            case FieldLocation.dim:
                return self._has_dim(data_source, name)
        return False

    def _read_value(
        self, data_source: DataSourceT, name: str, location: FieldLocation | None
    ) -> Any:
        """Read a physical name at its recorded location."""
        match location:
            case FieldLocation.attr:
                return self._get_attr(data_source, name)
            case FieldLocation.var:
                return self._read_var_values(self._get_var(data_source, name))
            case FieldLocation.dim:
                return self._get_dim(data_source, name)
        raise KeyError(name)

    def _read_value_or_default(
        self, data_source: DataSourceT | None, mapped: MappedField
    ) -> Any:
        """Read an existing mapped field, otherwise use its configured fallback."""
        if (
            data_source is not None
            and mapped.location is not None
            and self._has_field(data_source, mapped.name, mapped.location)
        ):
            return self._read_value(data_source, mapped.name, mapped.location)
        if mapped.value_default is not MISSING:
            return mapped.value_default
        msg = f"Field not found: {mapped.name}"
        raise KeyError(msg)

    def _has_attr(self, data_source: DataSourceT, name: str) -> bool:
        """Check for an attribute without reading it; default is False."""
        return False

    def _has_var(self, data_source: DataSourceT, name: str) -> bool:
        """Check for a variable without reading it; default is False."""
        return False

    def _has_dim(self, data_source: DataSourceT, name: str) -> bool:
        """Check for a dimension without reading arrays; default is False."""
        return False

    def _get_attr(self, data_source: DataSourceT, name: str) -> Any:
        """Return an attribute by physical name."""
        msg = f"{type(self).__name__} must implement _get_attr()"
        raise NotImplementedError(msg)

    def _get_var(self, data_source: DataSourceT, name: str) -> VariableT:
        """Return a native variable by physical name without loading its values."""
        msg = f"{type(self).__name__} must implement _get_var()"
        raise NotImplementedError(msg)

    def _get_dim(self, data_source: DataSourceT, name: str) -> int:
        """Return a dimension length, or raise KeyError for unsupported dimensions."""
        raise KeyError(name)

    def _read_var_values(self, var: VariableT) -> Any:
        """Materialize variable values; return var unchanged for plain-value sources."""
        return var

    def _read_scalar_var(self, var: VariableT) -> Any:
        """Read a scalar variable; unsupported variable types raise ValueError."""
        msg = f"Variables in {type(self).__name__} cannot be read as a scalar"
        raise ValueError(msg)

    def _read_str_var(self, var: VariableT) -> Any:
        """Read one string's values; unsupported variable types raise ValueError."""
        msg = f"Variables in {type(self).__name__} cannot be read as a single string"
        raise ValueError(msg)

    def validate_has_field(self, field: Mapping) -> None:
        """Validate that a required field was found during mapping.

        This checks the concrete plan resolved from the mapper's reference
        source. It does not inspect the source supplied to a later read.

        Parameters
        ----------
        field : Mapping
            Field mapping to validate

        Raises
        ------
        ValueError
            If field is missing from the schema mapping
        """
        if field not in self:
            field_name = self.get_name(field)
            if field_name is None and isinstance(field, NameMapping):
                field_name = field.names[0]
            if field_name is None:
                field_name = field
            msg = f"Missing required field {field_name!r}"
            raise ValueError(msg)


def _decode_str(value: Any, *, name: str, encoding: str) -> str:
    """Decode one in-memory string or character array and remove outer padding."""
    value = np.asarray(value)
    if value.ndim == 0 or (value.ndim == 1 and value.size == 1):
        text = value.item()
    elif value.ndim == 1 and value.dtype == "S1":
        text = value.tobytes()
    elif value.ndim == 1 and value.dtype == "U1":
        text = "".join(value.tolist())
    else:
        msg = f"Field {name!r} is not a single string"
        raise ValueError(msg)
    if isinstance(text, bytes):
        text = text.decode(encoding)
    if not isinstance(text, str):
        msg = f"Field {name!r} is not a single string"
        raise TypeError(msg)
    return text.strip("\x00 \t\r\n")
