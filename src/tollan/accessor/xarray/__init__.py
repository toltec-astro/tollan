"""Xarray-specific accessor components.

This package provides xarray-specialized components for building data accessors
and views with support for Dataset, DataArray, and DataTree.

Core Components
---------------
- XarrayMapper: Reads variables, coordinates, attributes, and dimension lengths
  from Dataset or DataArray payloads
- XarrayAccessorBase: Specialized accessor base class with DataTree support
- ensure_dataset: Utility to convert DataTree/DataArray to Dataset
- ensure_datatree: Utility to wrap Dataset/DataArray in DataTree

Examples
--------
Basic mapper usage:

    >>> import xarray as xr
    >>> from dataclasses import dataclass
    >>> from tollan.accessor import Mapping, NameMapping, Schema
    >>> from tollan.accessor.xarray import XarrayMapper
    >>>
    >>> @dataclass
    ... class DataSchema(Schema):
    ...     temperature: Mapping = NameMapping("temp")
    >>>
    >>> class DataMapper(XarrayMapper[DataSchema]):
    ...     pass
    >>>
    >>> ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
    >>> mapper = DataMapper.from_data_source(ds)
    >>> mapper.get_name(mapper.schema.temperature)
    'temp'

Using XarrayAccessorBase:

    >>> from tollan.accessor.xarray import XarrayAccessorBase
    >>>
    >>> @xr.register_dataset_accessor("data")
    ... class DataAccessor(XarrayAccessorBase[DataMapper]):
    ...     @property
    ...     def temp(self):
    ...         return self.mapper.get_arr(
    ...             self.data_source,
    ...             self.mapper.schema.temperature
    ...         )
    >>>
    >>> float(ds.data.temp[0])
    20.0
    >>> # Clean up
    >>> del xr.Dataset.data

DataTree support (automatic resolution):

    >>> dt = xr.DataTree(dataset=ds)
    >>> accessor = DataAccessor(dt)
    >>> isinstance(accessor._data_source, xr.DataTree)
    True
    >>> isinstance(accessor.data_source, xr.Dataset)
    True

Utilities for data source conversion:

    >>> from tollan.accessor.xarray import ensure_dataset, ensure_datatree
    >>> ds = xr.Dataset({"temp": (["x"], [20.0])})
    >>> dt = ensure_datatree(ds)
    >>> isinstance(dt, xr.DataTree)
    True
    >>> ds2 = ensure_dataset(dt)
    >>> isinstance(ds2, xr.Dataset)
    True
"""

from __future__ import annotations

from .accessor import XarrayAccessorBase
from .mapper import XarrayMapper
from .units import UnitsAccessor
from .utils import (
    XarrayPayloadT,
    XarraySourceT,
    ensure_dataset,
    ensure_datatree,
    unwrap_data_source,
)

__all__ = [
    "UnitsAccessor",
    "XarrayAccessorBase",
    "XarrayMapper",
    "XarrayPayloadT",
    "XarraySourceT",
    "ensure_dataset",
    "ensure_datatree",
    "unwrap_data_source",
]
