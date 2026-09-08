"""Xarray-specific accessor components.

This module provides XarrayAccessorBase for building data accessors with
Dataset, DataArray, and DataTree support.

Example
-------
    >>> import xarray as xr
    >>> from dataclasses import dataclass
    >>> from tollan.accessor import Mapping, NameMapping, Schema
    >>> from tollan.accessor.xarray import XarrayMapper, XarrayAccessorBase
    >>>
    >>> # Define schema
    >>> @dataclass
    ... class DataSchema(Schema):
    ...     temperature: Mapping = NameMapping("temp")
    >>>
    >>> # Define mapper
    >>> class DataMapper(XarrayMapper[DataSchema]):
    ...     pass
    >>>
    >>> # Define accessor
    >>> class DataAccessor(XarrayAccessorBase[DataMapper]):
    ...     @property
    ...     def temp(self):
    ...         return self.mapper.get_arr(
    ...             self.data_source,
    ...             self.mapper.schema.temperature
    ...         )
    >>>
    >>> # Use with Dataset
    >>> ds = xr.Dataset({"temp": (["x"], [20.0, 21.0, 22.0])})
    >>> accessor = DataAccessor(ds)
    >>> float(accessor.temp[0])
    20.0
    >>>
    >>> # Works with DataTree (auto-resolves to root dataset)
    >>> dt = xr.DataTree(dataset=ds)
    >>> accessor = DataAccessor(dt)
    >>> float(accessor.temp[0])
    20.0
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, cast

from ..accessor import AccessorBase
from ..mapper import Mapper
from .utils import XarraySourceT, ensure_dataset

if TYPE_CHECKING:
    import xarray as xr

__all__ = ["XarrayAccessorBase"]


class XarrayAccessorBase[MapperT: Mapper](AccessorBase[XarraySourceT, MapperT]):
    """Accessor base class for xarray with DataTree support.

    Extends AccessorBase to handle Dataset, DataArray, and DataTree objects.
    Stores the original data source and provides automatic resolution to Dataset.

    Type Parameters
    ---------------
    MapperT : Mapper
        Type of mapper for field resolution
    """

    def __init__(
        self,
        data_source: XarraySourceT,
        mapper: MapperT | None = None,
    ) -> None:
        """Initialize with xarray data source.

        Parameters
        ----------
        data_source : Dataset, DataArray, or DataTree
            Xarray data source to access
        mapper : MapperT, optional
            Field mapper. If None, creates from resolved Dataset.
        """
        self._data_source = data_source

        if mapper is None:
            mapper_cls = cast("type[MapperT]", type(self)._mapper_cls)
            mapper = mapper_cls.from_data_source(self.data_source)
        self._mapper = mapper

        self._validate()

    @functools.cached_property
    def data_source(self) -> xr.Dataset:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Return the source normalized to a Dataset."""
        return ensure_dataset(self._data_source)
