"""Xarray-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import xarray as xr

    from ..schema import Mapping

from ..mapper import Mapper
from ..schema import Schema

__all__ = ["XarrayMapper"]


class XarrayMapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for xarray.Dataset.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)
    """

    def _has_field(self, data_source: xr.Dataset, name: str) -> bool:
        """Check if field exists as data variable, coordinate, or attribute."""
        return (
            name in data_source.data_vars
            or name in data_source.coords
            or name in data_source.attrs
        )

    def _read_value(self, data_source: xr.Dataset, name: str) -> Any:
        """Read field value from dataset.

        Returns the underlying numpy array for data variables/coords,
        or the raw attribute value for attributes.
        """
        if name in data_source.attrs:
            return np.array(data_source.attrs[name])
        return data_source[name].values

    def get_arr(self, data_source: xr.Dataset, field: Mapping) -> xr.DataArray:
        """Get DataArray for a schema field.

        Parameters
        ----------
        data_source : xr.Dataset
            Dataset to read from
        field : Mapping
            Field mapping from schema

        Returns
        -------
        xr.DataArray
            DataArray from dataset

        Raises
        ------
        ValueError
            If field not found in dataset
        """
        if not self.has(field):
            msg = f"Field '{field.names[0]}' not found in dataset"
            raise ValueError(msg)
        name = self.get_name(field)
        return data_source[name]

    def get_coord(self, data_source: xr.Dataset, field: Mapping) -> xr.DataArray:
        """Get coordinate DataArray for a schema field.

        Parameters
        ----------
        data_source : xr.Dataset
            Dataset to read from
        field : Mapping
            Field mapping from schema

        Returns
        -------
        xr.DataArray
            Coordinate DataArray

        Raises
        ------
        ValueError
            If field not found or not a coordinate
        """
        if not self.has(field):
            msg = f"Field '{field.names[0]}' not found in dataset"
            raise ValueError(msg)
        name = self.get_name(field)
        coord = data_source.coords.get(name, None)
        if coord is None:
            msg = f"Field '{field.names[0]}' is not a coordinate"
            raise ValueError(msg)
        return coord

    def get_scalar(self, data_source: xr.Dataset, field: Mapping) -> Any:
        """Get scalar value for a schema field.

        Parameters
        ----------
        data_source : xr.Dataset
            Dataset to read from
        field : Mapping
            Field mapping from schema

        Returns
        -------
        scalar
            Scalar value from dataset or attrs

        Raises
        ------
        ValueError
            If field not found in dataset or is not a scalar
        """
        if not self.has(field):
            msg = f"Field '{field.names[0]}' not found in dataset"
            raise ValueError(msg)
        name = self.get_name(field)

        # Check if it's in attrs first
        if name in data_source.attrs:
            return data_source.attrs[name]

        # Check if it's a variable
        if name in data_source:
            var = data_source[name]
            # If it's a scalar or 0-D, return the value
            if var.ndim == 0:
                return var.item()
            # If it's 1-D with one element, return that element
            if var.size == 1:
                return var.values.flat[0]

        msg = f"Field '{field.names[0]}' is not a scalar"
        raise ValueError(msg)

    def get_shape(self, data_source: xr.Dataset, field: Mapping) -> tuple[int, ...]:
        """Get shape of a field's data array.

        Parameters
        ----------
        data_source : xr.Dataset
            Dataset to read from
        field : Mapping
            Field mapping from schema

        Returns
        -------
        tuple[int, ...]
            Shape of the data array

        Raises
        ------
        ValueError
            If field not found in dataset
        """
        arr = self.get_arr(data_source, field)
        return arr.shape
