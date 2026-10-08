"""Base mapper class for resolving flat schemas and accessing data."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator
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
    """Resolve schema fields and provide a data access interface.

    Use ``from_data_source`` to resolve a schema for a particular source, then
    pass a source and schema field to the read methods. A mapper can be reused
    across a batch of sources with compatible layouts. Each read requires only
    the resolved names and paths it uses; unused fields may be absent and extra
    fields do not prevent reuse.

    Notes
    -----
    Bind these type parameters when subclassing:

    ``SchemaT``
        Schema class defining the fields to resolve.
    ``DataSourceT``
        Source type accepted by this mapper. Defaults to Any; storage-specific
        mapper classes supply their source type.
    ``VariableT``
        Native variable type returned by ``get_var()``. Defaults to Any.
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
        """Initialize a mapper from existing resolution records.

        Parameters
        ----------
        mapped_fields : mapping, optional
            Existing resolution records keyed by schema mappings. ``None`` creates
            an empty mapper. Use ``from_data_source`` to resolve against data.
        """
        self._mapped_fields = dict(mapped_fields or {})
        self._mapped_fields_view = MappingProxyType(self._mapped_fields)

    def __getstate__(self) -> dict[str, Any]:
        """Return picklable mapper state."""
        state = self.__dict__.copy()
        del state["_mapped_fields_view"]
        field_names = {
            mapping: field.name
            for field in fields(self.schema)
            if isinstance(mapping := getattr(self.schema, field.name), Mapping)
        }
        state["_mapped_fields"] = {
            field_names.get(mapping, mapping): mapped_field
            for mapping, mapped_field in self._mapped_fields.items()
        }
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore field bindings without resolving against a source."""
        self.__dict__.update(state)
        self._mapped_fields = {}
        for key, mapped_field in state["_mapped_fields"].items():
            mapping = getattr(self.schema, key) if isinstance(key, str) else key
            self._mapped_fields[mapping] = replace(mapped_field, mapping=mapping)
        self._mapped_fields_view = MappingProxyType(self._mapped_fields)

    @property
    def mapped_fields(self) -> MappingABC[Mapping, MappedField]:
        """Read-only resolution records keyed by schema mappings."""
        return self._mapped_fields_view

    @classmethod
    def from_data_source(
        cls,
        data_source: DataSourceT | None,
        defaults: dict[Mapping, Any] | None = None,
    ) -> Self:
        """Resolve the schema against a data source.

        Parameters
        ----------
        data_source : DataSourceT or None
            Container used to select candidate names and paths. ``None`` selects
            the first candidate of each field without inspecting data.
        defaults : dict[Mapping, Any] | None
            Fallbacks used by get_value_or_default() and eager resolution when
            the field is absent. Retained even when data_source has the field.

        Returns
        -------
        Self
            Mapper with resolved field mappings.
        """
        mapper = cls()
        mapper._populate_from_schema(data_source, defaults or {})
        return mapper

    @classmethod
    def from_defaults(
        cls,
        defaults: dict[Mapping, Any] | None = None,
    ) -> Self:
        """Resolve the schema without a data source.

        Parameters
        ----------
        defaults : dict[Mapping, Any] | None
            Fallback values keyed by schema mappings. These are values, not
            replacement names or paths.

        Returns
        -------
        Self
            Mapper containing first-candidate names and paths with the supplied
            fallback values.
        """
        return cls.from_data_source(
            data_source=None,
            defaults=defaults,
        )

    def _iter_schema_mappings(
        self, context: MappingContext
    ) -> Iterator[tuple[str, Mapping, MappingContext]]:
        """Yield schema names, mappings, and contexts in declaration order."""
        for field in fields(context.schema):
            mapping = getattr(context.schema, field.name)
            if isinstance(mapping, Mapping):
                yield field.name, mapping, context

    def _prepare_mapping_context(
        self, context: MappingContext, defaults: dict[Mapping, Any]
    ) -> MappingContext:
        """Prepare the context for schema field resolution.

        Parameters
        ----------
        context : MappingContext
            Source, schema, and existing mappings.
        defaults : dict[Mapping, Any]
            Fallback values keyed by schema mappings.

        Returns
        -------
        MappingContext
            Context for the schema iterator. The base implementation returns
            the supplied context unchanged.
        """
        return context

    def _populate_from_schema(
        self,
        data_source: DataSourceT | None,
        defaults: dict[Mapping, Any],
    ) -> None:
        """Populate resolution records for the schema's mapping declarations.

        Parameters
        ----------
        data_source : DataSourceT or None
            Data source used to resolve the schema mappings.
        defaults : dict[Mapping, Any]
            Fallback values keyed by schema mappings.
        """
        schema = cast("SchemaT", type(self).schema)
        context_initial = MappingContext(
            data_source=data_source,
            schema=schema,
            mapped_fields=self.mapped_fields,
        )
        context_initial = self._prepare_mapping_context(context_initial, defaults)

        for field_name, mapping, context in self._iter_schema_mappings(context_initial):
            value_default = defaults.get(mapping, MISSING)

            self._mapped_fields[mapping] = self._resolve_mapping(
                mapping=mapping,
                field_name=field_name,
                value_default=value_default,
                context=context,
            )

    def _resolve_mapping(
        self,
        mapping: Mapping,
        field_name: str,
        value_default: Any,
        context: MappingContext,
    ) -> MappedField:
        """Select one field's data location from its candidate specification.

        Parameters
        ----------
        mapping : Mapping
            Schema declaration whose ``resolve`` method supplies a ``NameMapping``.
        field_name : str
            Schema attribute name for this mapping.
        value_default : Any
            Fallback value retained in the resolution record.
        context : MappingContext
            Data source, concrete schema, and previously resolved fields.

        Returns
        -------
        MappedField
            Selected name, entity kind, containing path, and optional captured value.
        """
        schema_path = context.schema.get_schema_path(field_name)
        mapping_resolved = mapping.resolve(context)
        parent_path = None
        data_source = context.data_source
        data_source_lookup = data_source
        if mapping_resolved.parent is not None:
            parent_path = self._get_parent_path(mapping_resolved.parent, context)
            if data_source is not None:
                data_source_lookup = (
                    self._get_node(data_source, parent_path)
                    if self._has_node(data_source, parent_path)
                    else None
                )
        mapped_field = None

        if data_source_lookup is not None:
            for candidate in mapping_resolved.candidates:
                location = self._resolve_location(
                    data_source_lookup, candidate.name, candidate.location
                )
                if location is not None:
                    mapped_field = MappedField(
                        mapping=mapping,
                        mapping_resolved=mapping_resolved,
                        name=candidate.name,
                        location=location,
                        value_default=value_default,
                        source=MappedFieldSource.data_source,
                        schema_path=schema_path,
                        parent_path=parent_path,
                    )
                    break

        if mapped_field is None:
            candidate = mapping_resolved.candidates[0]
            mapped_field = MappedField(
                mapping=mapping,
                mapping_resolved=mapping_resolved,
                name=candidate.name,
                location=candidate.location,
                value_default=value_default,
                source=(
                    MappedFieldSource.default
                    if value_default is not MISSING
                    else MappedFieldSource.missing
                ),
                schema_path=schema_path,
                parent_path=parent_path,
            )

        if (
            mapping_resolved.resolve_value
            and mapped_field.source != MappedFieldSource.missing
        ):
            mapped_field = replace(
                mapped_field,
                value=self._read_value_or_default(data_source, mapped_field),
            )
        return mapped_field

    def _get_parent_path(self, parent: NameMapping, context: MappingContext) -> str:
        """Compose the containing path from the parent's existing resolution record."""
        if FieldLocation.path not in self._supported_locations:
            msg = f"{type(self).__name__} does not support mapping parents"
            raise ValueError(msg)
        parent_field_name = context.schema._get_path_field_name(parent)
        if parent_field_name is not None:
            parent = getattr(context.schema, parent_field_name)
        parent_mapped_field = context.mapped_fields.get(parent)
        if parent_mapped_field is None:
            msg = "A parent mapping must be declared before its child in the schema"
            raise ValueError(msg)
        if parent_mapped_field.location != FieldLocation.path:
            msg = "A mapping parent must resolve to a subtree"
            raise ValueError(msg)
        return str(
            PurePosixPath(parent_mapped_field.parent_path or ".")
            / parent_mapped_field.name
        )

    def __contains__(self, mapping: Mapping) -> bool:
        """Return whether the schema field was found during mapper resolution.

        Parameters
        ----------
        mapping : Mapping
            Schema field reference (e.g., schema.temp)

        Returns
        -------
        bool
            Whether the resolution record identifies data found in the source
            used to construct this mapper. This does not inspect a current source.
        """
        mapped_field = self.mapped_fields.get(mapping)
        return (
            mapped_field.source == MappedFieldSource.data_source
            if mapped_field
            else False
        )

    def get_name(self, mapping: Mapping) -> str | None:
        """Return the selected data name or subtree path for a schema field.

        For fields resolved from a data source, returns the actual field name found.
        For fields with default values or missing fields, returns the first name
        from the mapping's candidate list.

        Parameters
        ----------
        mapping : Mapping
            Schema field reference

        Returns
        -------
        str | None
            Physical field name, or None if mapping not resolved
        """
        mapped_field = self.mapped_fields.get(mapping)
        return mapped_field.name if mapped_field else None

    def get_value(self, data_source: DataSourceT, mapping: Mapping) -> Any:
        """Read a field value from the supplied data source.

        Values captured during mapping resolution remain available in
        ``mapped_fields[mapping].value``, but do not replace a
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
        mapped_field = self.mapped_fields.get(mapping)

        if mapped_field is None or mapped_field.location is None:
            msg = f"Field not found: {mapping}"
            raise KeyError(msg)
        if mapped_field.parent_path is not None:
            data_source = self._get_node(data_source, mapped_field.parent_path)

        return self._read_value(
            data_source,
            mapped_field.name,
            mapped_field.location,
        )

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
        mapped_field = self.mapped_fields[mapping]
        return self._read_value_or_default(data_source, mapped_field)

    def has_attr(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Return whether the mapped attribute exists in the supplied source.

        Parameters
        ----------
        data_source : DataSourceT
            Source to inspect at the recorded parent path and name.
        field : Mapping
            Schema mapping for the attribute.

        Returns
        -------
        bool
            Whether the attribute exists at its mapped location. Unknown mappings
            and mappings for other locations return False.
        """
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location != FieldLocation.attr:
            return False
        if mapped_field.parent_path is not None:
            if not self._has_node(data_source, mapped_field.parent_path):
                return False
            data_source = self._get_node(data_source, mapped_field.parent_path)
        return self._has_attr(data_source, mapped_field.name)

    def has_var(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Return whether the mapped variable exists in the supplied source.

        Parameters
        ----------
        data_source : DataSourceT
            Source to inspect at the recorded parent path and name.
        field : Mapping
            Schema mapping for the variable.

        Returns
        -------
        bool
            Whether the variable exists at its mapped location. Unknown mappings
            and mappings for other locations return False.
        """
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location != FieldLocation.var:
            return False
        if mapped_field.parent_path is not None:
            if not self._has_node(data_source, mapped_field.parent_path):
                return False
            data_source = self._get_node(data_source, mapped_field.parent_path)
        return self._has_var(data_source, mapped_field.name)

    def get_var(self, data_source: DataSourceT, field: Mapping) -> VariableT:
        """Return the native variable without requesting its values.

        Returns a DataArray for xarray, a Variable for netCDF4, or a Series for
        pandas. Labels, metadata, and the variable's backend remain available.
        Defaults do not substitute for a native variable.

        Parameters
        ----------
        data_source : DataSourceT
            Source to read at the recorded parent path and name.
        field : Mapping
            Schema mapping identifying the data to read.

        Returns
        -------
        VariableT
            Native variable with its backend and metadata preserved.

        Raises
        ------
        ValueError
            If the mapping is absent or selects a non-variable location.
        KeyError
            If the variable does not exist in the supplied source.
        """
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location != FieldLocation.var:
            msg = (
                f"Field {self.get_name(field) or field!r} not found as a variable "
                f"in {type(data_source).__name__}"
            )
            raise ValueError(msg)
        if mapped_field.parent_path is not None:
            data_source = self._get_node(data_source, mapped_field.parent_path)
        return self._get_var(data_source, mapped_field.name)

    def get_scalar(self, data_source: DataSourceT, field: Mapping) -> Any:
        """Read an attribute, scalar variable, or dimension length.

        Attributes are returned unchanged. Variable reads use the backend's
        scalar rules: xarray and netCDF4 accept 0-D variables and single-element
        string variables; pandas columns are not scalars. Bytes remain bytes.
        Variable shape is checked before loading values. This method reads the
        supplied source, not defaults or captured resolution values.

        Parameters
        ----------
        data_source : DataSourceT
            Source to read at the recorded parent path and name.
        field : Mapping
            Schema mapping identifying the data to read.

        Returns
        -------
        Any
            Attribute value, scalar variable value, or dimension length.

        Raises
        ------
        ValueError
            If the mapping has no known location or the variable is not scalar.
        KeyError
            If the variable or dimension is absent from the supplied source.
        """
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location in (None, FieldLocation.path):
            msg = (
                f"Field {self.get_name(field) or field!r} "
                f"not found in {type(data_source).__name__}"
            )
            raise ValueError(msg)
        if mapped_field.parent_path is not None:
            data_source = self._get_node(data_source, mapped_field.parent_path)
        if mapped_field.location == FieldLocation.var:
            return self._read_scalar_var(self._get_var(data_source, mapped_field.name))
        return self._read_value(
            data_source,
            mapped_field.name,
            mapped_field.location,
        )

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

        Parameters
        ----------
        data_source : DataSourceT
            Source to read at the recorded parent path and name.
        field : Mapping
            Schema mapping identifying the data to read.
        encoding : str, default "utf-8"
            Character encoding used to decode bytes.

        Returns
        -------
        str
            Decoded text with outer null and whitespace padding removed.

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
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location is None:
            msg = f"Field not found: {field}"
            raise KeyError(msg)
        if mapped_field.parent_path is not None:
            data_source = self._get_node(data_source, mapped_field.parent_path)
        if mapped_field.location == FieldLocation.var:
            value = self._read_str_var(self._get_var(data_source, mapped_field.name))
        else:
            value = self._read_value(
                data_source,
                mapped_field.name,
                mapped_field.location,
            )
        return _decode_str(value, name=mapped_field.name, encoding=encoding)

    def has_dim(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Return whether the mapped dimension exists in the supplied source.

        Parameters
        ----------
        data_source : DataSourceT
            Source to inspect at the recorded parent path and name.
        field : Mapping
            Schema mapping for the dimension.

        Returns
        -------
        bool
            Whether the dimension exists at its mapped location. Unknown mappings
            and mappings for other locations return False.
        """
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location != FieldLocation.dim:
            return False
        if mapped_field.parent_path is not None:
            if not self._has_node(data_source, mapped_field.parent_path):
                return False
            data_source = self._get_node(data_source, mapped_field.parent_path)
        return self._has_dim(data_source, mapped_field.name)

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
        mapped_field = self.mapped_fields.get(field)
        if mapped_field is None or mapped_field.location != FieldLocation.dim:
            msg = f"Dimension not found: {field}"
            raise KeyError(msg)
        if mapped_field.parent_path is not None:
            data_source = self._get_node(data_source, mapped_field.parent_path)
        return self._get_dim(data_source, mapped_field.name)

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
            case FieldLocation.path:
                return self._has_node(data_source, name)
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
            case FieldLocation.path:
                return self._get_node(data_source, name)
        raise KeyError(name)

    def _read_value_or_default(
        self, data_source: DataSourceT | None, mapped_field: MappedField
    ) -> Any:
        """Read a mapped value, or return its configured fallback."""
        if data_source is not None and mapped_field.parent_path is not None:
            data_source = (
                self._get_node(data_source, mapped_field.parent_path)
                if self._has_node(data_source, mapped_field.parent_path)
                else None
            )
        if (
            data_source is not None
            and mapped_field.location is not None
            and self._has_field(data_source, mapped_field.name, mapped_field.location)
        ):
            return self._read_value(
                data_source, mapped_field.name, mapped_field.location
            )
        if mapped_field.value_default is not MISSING:
            return mapped_field.value_default
        msg = f"Field not found: {mapped_field.name}"
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

    def _has_node(self, data_source: DataSourceT, path: str) -> bool:
        """Check for a subtree at a path without loading arrays; default is False."""
        return False

    def _get_node(self, data_source: DataSourceT, path: str) -> Any:
        """Return a native subtree at a path, or raise KeyError when unsupported."""
        raise KeyError(path)

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

        This checks the resolution record created during mapper construction.
        It does not inspect the source supplied to a later read.

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
