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
