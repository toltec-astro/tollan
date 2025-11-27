"""Infrastructure for schema-driven data accessors.

This module provides a flexible, predicate-based framework for building type-safe
data accessors. It resolves the challenge of accessing data variables that may have
different names across datasets or depend on runtime conditions.

Core Concepts:
    - FieldMapping: Field definition with physical name candidates, resolution flags
    - Mapping: Concrete FieldMapping for direct field access
    - MappingBase: Abstract base for conditional field resolution
    - Schema: Dataclass with Mapping fields defining logical→physical name mappings
    - Mapper[SchemaT]: Generic translator that resolves schema against data source,
                       stores resolved names and values (when requested)
    - MappedField: Resolution result with name, value, and metadata

Key Features:
    - Maximum flexibility with arbitrary Python predicates
    - Sequential resolution: later predicates access earlier results
    - Value storage: both resolved name AND loaded value (when requested)
    - Load control: fine-grained control over immediate vs deferred loading
    - No prescribed workflow: schema defines its own resolution logic
    - Generic type safety: Mapper[SchemaT] for IDE support
    - Works with any data container: xarray, pandas, HDF5, NetCDF, etc.

Example:
    >>> from dataclasses import dataclass
    >>> from tollan.accessor import Schema, Mapping, Mapper
    >>>
    >>> # Define schema with field mappings
    >>> @dataclass
    ... class MySchema(Schema):
    ...     data_kind: Mapping = Mapping(
    ...         ("kind", "type"),
    ...         required=True,
    ...         resolve_value=True  # Load immediately
    ...     )
    ...     temperature: Mapping = Mapping(
    ...         ("temp_raw", "temperature", "temp_calibrated"),
    ...         required=False,
    ...         resolve_value=False  # Defer loading
    ...     )
    >>>
    >>> # Resolve against data (would use real data source)
    >>> # mapper = Mapper(data_source, MySchema)
    >>> # kind = mapper.get_value("data_kind")  # Loaded value
    >>> # temp_name = mapper.get_name("temperature")  # Field name only
    >>> # temp_data = data_source[temp_name]  # Load from source
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
