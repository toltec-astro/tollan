"""Infrastructure for schema-driven data accessors.

This module provides a flexible framework for building type-safe data accessors.
It resolves the challenge of accessing data variables that may have different names
across datasets or depend on runtime conditions.

Core Concepts:
    - Mapping: Field definition with physical name candidates and resolution flags
    - MappingBase: Base class for custom mapping strategies
    - Schema: Dataclass with Mapping fields defining logical→physical name mappings
    - Mapper[SchemaT]: Generic translator that resolves schema against data source,
                       stores resolved names and values (when requested)
    - MappedField: Resolution result with name, value, and metadata

Key Features:
    - Flexible resolution: Try multiple physical names per logical field
    - Conditional mappings: Subclass MappingBase for context-dependent resolution
    - Lazy loading: Fine-grained control over immediate vs deferred value loading
    - Type safety: Generic Mapper[SchemaT] for IDE support and type checking
    - Multiple backends: Built-in support for xarray, pandas, and NetCDF4
    - Extensible: Implement _has_field() and _read_value() for custom data sources

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
    "MappedField",
    "Mapper",
    "Mapping",
    "MappingBase",
    "Schema",
]

from .mapper import Mapper
from .schema import (
    MISSING,
    MappedField,
    Mapping,
    MappingBase,
    Schema,
)
