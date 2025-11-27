"""Infrastructure for schema-driven data accessors.

This module provides a flexible, predicate-based framework for building type-safe
data accessors. It resolves the challenge of accessing data variables that may have
different names across datasets or depend on runtime conditions.

Core Concepts:
    - FieldDef: Field definition with resolution logic (candidates OR predicates),
                value storage (resolved name + loaded value), and load control
    - Schema: Dict-like mapping from logical names to FieldDef instances
              Resolution happens in insertion order for sequential dependencies
    - Mapper[SchemaT]: Generic translator that resolves schema against data,
                       stores resolved names and values (if loaded)
    - Context: Multi-mapper container propagating through operations
    - ContextHandler: Storage/retrieval of context in data.attrs

Key Features:
    - Maximum flexibility with arbitrary Python predicates
    - Sequential resolution: later predicates access earlier results
    - Value storage: both resolved name AND loaded value (when requested)
    - Load control: fine-grained control over immediate vs deferred loading
    - No prescribed workflow: schema defines its own resolution logic
    - Generic type safety: Mapper[SchemaT] for IDE support
    - Works with any data container: xarray, pandas, HDF5, NetCDF, etc.

Example:
    >>> from tollan.accessor import Schema, FieldDef, Mapper
    >>>
    >>> # Define schema with predicates
    >>> SCHEMA = Schema(
    ...     data_kind=FieldDef(
    ...         names=("kind", "type"),
    ...         load_value=True,  # Load immediately
    ...         required=True
    ...     ),
    ...     temperature_raw=FieldDef(
    ...         names=("temp_raw", "temperature"),
    ...         predicate=lambda data, resolved: (
    ...             resolved["data_kind"].value == "raw"
    ...         ),
    ...         load_value=False,  # Defer loading
    ...         required=False
    ...     ),
    ...     temperature_calibrated=FieldDef(
    ...         names=("temp_calibrated", "temp_cal"),
    ...         predicate=lambda data, resolved: (
    ...             resolved["data_kind"].value == "processed"
    ...         ),
    ...         load_value=False,
    ...         required=False
    ...     ),
    ... )
    >>>
    >>> # Resolve against data
    >>> mapper = Mapper.from_schema(SCHEMA, ds)
    >>> kind = mapper.get_value("data_kind")  # Loaded value
    >>>
    >>> # Only one temperature field will be in mapper
    >>> if mapper.has("temperature_raw"):
    ...     temp_var = mapper.get_name("temperature_raw")
    >>> elif mapper.has("temperature_calibrated"):
    ...     temp_var = mapper.get_name("temperature_calibrated")
    >>> temp_data = ds[temp_var]  # Load from dataset
"""

from __future__ import annotations

__all__ = [
    "MISSING",
    "FieldMapping",
    "MappedField",
    "Mapper",
    "Mapping",
    "MappingBase",
    "Schema",
    "XarrayMapper",
]

from .mapper import Mapper
from .mappers import XarrayMapper
from .schema import (
    MISSING,
    FieldMapping,
    MappedField,
    Mapping,
    MappingBase,
    Schema,
)
