"""Xarray-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import xarray as xr

from ..mapper import Mapper
from ..schema import Schema

__all__ = ["XarrayMapper"]


class XarrayMapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for xarray.Dataset.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)

    Parameters
    ----------
    data_source : xr.Dataset
        The xarray Dataset to map fields from
    default_values : dict[MappingBase, Any], optional
        Default values for fields not found in the dataset
    """

    data_source: xr.Dataset

    def _has_field(self, name: str) -> bool:
        """Check if field exists as data variable, coordinate, or attribute."""
        return (
            name in self.data_source.data_vars
            or name in self.data_source.coords
            or name in self.data_source.attrs
        )

    def _read_value(self, name: str) -> Any:
        """Read field value from dataset.

        Returns the underlying numpy array for data variables/coords,
        or the raw attribute value for attributes.
        """
        if name in self.data_source.attrs:
            return np.array(self.data_source.attrs[name])
        return self.data_source[name].values
