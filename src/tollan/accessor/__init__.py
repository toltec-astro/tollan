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
    - AccessorBase: Base class for building data accessors and views with automatic
                    mapper creation and type detection

Key Features:
    - Flexible resolution: Try multiple physical names per logical field
    - Conditional mappings: Subclass MappingBase for context-dependent resolution
    - Lazy loading: Fine-grained control over immediate vs deferred value loading
    - Type safety: Generic Mapper[SchemaT] for IDE support and type checking
    - Multiple backends: Built-in support for xarray, pandas, and NetCDF4
    - Extensible: Implement _has_field() and _read_value() for custom data sources

Examples
--------
Basic mapper usage with xarray:

    >>> from dataclasses import dataclass
    >>> import xarray as xr
    >>> from tollan.accessor import Schema, Mapping, AccessorBase
    >>> from tollan.accessor.xarray import XarrayMapper
    >>>
    >>> # Define schema with field mappings
    >>> @dataclass
    ... class DataSchema(Schema):
    ...     temperature: Mapping = Mapping(("temp", "temperature", "T"))
    ...     pressure: Mapping = Mapping(("press", "pressure", "P"))
    >>>
    >>> # Define mapper
    >>> class DataMapper(XarrayMapper[DataSchema]):
    ...     pass
    >>>
    >>> # Create test dataset
    >>> ds = xr.Dataset({
    ...     "temp": ("x", [20.0, 21.0, 22.0]),
    ...     "press": ("x", [101.3, 101.4, 101.5])
    ... })
    >>>
    >>> # Use mapper directly
    >>> mapper = DataMapper.from_data_source(ds)
    >>> mapper.schema.temperature in mapper
    True
    >>> temp_name = mapper.get_name(mapper.schema.temperature)
    >>> temp_name
    'temp'
    >>> temp_data = mapper.get_arr(ds, mapper.schema.temperature)
    >>> float(temp_data[0])
    20.0

Using AccessorBase to create xarray accessor:

    >>> @xr.register_dataset_accessor("data")
    ... class DataAccessor(AccessorBase[xr.Dataset, DataMapper]):
    ...     @property
    ...     def temp_celsius(self):
    ...         return self.mapper.get_arr(
    ...             self.data_source,
    ...             self.mapper.schema.temperature
    ...         )
    >>>
    >>> # Use as xarray accessor
    >>> float(ds.data.temp_celsius[0])
    20.0
    >>> # Clean up accessor
    >>> del xr.Dataset.data

Using AccessorBase as data view:

    >>> class DataView(AccessorBase[xr.Dataset, DataMapper]):
    ...     def _validate(self):
    ...         # Ensure required fields exist
    ...         if self.mapper.schema.temperature not in self.mapper:
    ...             raise ValueError("Missing temperature field")
    ...
    ...     @property
    ...     def temp_range(self):
    ...         temp = self.mapper.get_arr(
    ...             self.data_source,
    ...             self.mapper.schema.temperature
    ...         )
    ...         return float(temp.min()), float(temp.max())
    >>>
    >>> view = DataView(ds)
    >>> view.temp_range
    (20.0, 22.0)

Generic data sources (not just xarray):

    >>> from typing import Any
    >>> from tollan.accessor import Mapper
    >>>
    >>> # Define schema
    >>> @dataclass
    ... class ConfigSchema(Schema):
    ...     host: Mapping = Mapping("host")
    ...     port: Mapping = Mapping("port")
    >>>
    >>> # Define mapper for dict data source
    >>> class DictMapper(Mapper[ConfigSchema]):
    ...     def _has_field(self, data_source: dict[str, Any], name: str) -> bool:
    ...         return name in data_source
    ...
    ...     def _read_value(self, data_source: dict[str, Any], name: str):
    ...         return data_source[name]
    >>>
    >>> # Define accessor
    >>> class ConfigAccessor(AccessorBase[dict[str, Any], DictMapper]):
    ...     @property
    ...     def endpoint(self):
    ...         host = self.mapper.get_value(
    ...             self.data_source,
    ...             self.mapper.schema.host
    ...         )
    ...         port = self.mapper.get_value(
    ...             self.data_source,
    ...             self.mapper.schema.port
    ...         )
    ...         return f"{host}:{port}"
    >>>
    >>> config = {"host": "localhost", "port": 8080}
    >>> accessor = ConfigAccessor(config)
    >>> accessor.endpoint
    'localhost:8080'
"""

from __future__ import annotations

from .accessor import AccessorBase
from .mapper import Mapper
from .schema import (
    MISSING,
    MappedField,
    Mapping,
    MappingBase,
    Schema,
)

__all__ = [
    "MISSING",
    "AccessorBase",
    "MappedField",
    "Mapper",
    "Mapping",
    "MappingBase",
    "Schema",
]
