"""netCDF4 Dataset-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from ..mapper import Mapper
from ..schema import Schema

if TYPE_CHECKING:
    import netCDF4 as nc  # noqa: N813


__all__ = ["NetCDF4Mapper"]


class NetCDF4Mapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for netCDF4.Dataset.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)
    """

    def _has_field(self, data_source: nc.Dataset, name: str) -> bool:
        """Check if field exists as variable, dimension, or attribute."""
        return (
            name in data_source.variables
            or name in data_source.dimensions
            or hasattr(data_source, name)
        )

    def _read_value(self, data_source: nc.Dataset, name: str) -> Any:
        """Read field value from dataset.

        Returns the underlying numpy array for variables,
        or the attribute value for attributes.
        """
        if name in data_source.variables:
            return np.array(data_source.variables[name][:])
        if hasattr(data_source, name):
            return np.array(getattr(data_source, name))
        msg = f"Field {name} not found in dataset"
        raise KeyError(msg)
