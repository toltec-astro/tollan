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

    Parameters
    ----------
    data_source : nc.Dataset
        The netCDF4 Dataset to map fields from
    default_values : dict[MappingBase, Any], optional
        Default values for fields not found in the dataset
    """

    data_source: nc.Dataset

    def _has_field(self, name: str) -> bool:
        """Check if field exists as variable, dimension, or attribute."""
        return (
            name in self.data_source.variables
            or name in self.data_source.dimensions
            or hasattr(self.data_source, name)
        )

    def _read_value(self, name: str) -> Any:
        """Read field value from dataset.

        Returns the underlying numpy array for variables,
        or the attribute value for attributes.
        """
        if name in self.data_source.variables:
            return np.array(self.data_source.variables[name][:])
        if hasattr(self.data_source, name):
            return np.array(getattr(self.data_source, name))
        msg = f"Field {name} not found in dataset"
        raise KeyError(msg)
