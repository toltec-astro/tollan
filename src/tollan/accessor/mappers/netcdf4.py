"""netCDF4 Dataset-specific mapper implementation."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import numpy as np

# Suppress numpy ABI warning for netCDF4
warnings.filterwarnings(
    "ignore",
    message="numpy.ndarray size changed",
    category=RuntimeWarning,
)

if TYPE_CHECKING:
    import netCDF4 as nc  # noqa: N813

from ..mapper import Mapper
from ..schema import Schema

__all__ = ["NetCDF4Mapper"]


class NetCDF4Mapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for netCDF4.Dataset.

    Create via factory methods:
    - NetCDF4Mapper.from_data_source(dataset)
    - NetCDF4Mapper.from_resolved(resolved_dict)

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)

    Parameters
    ----------
    resolved : dict[int, MappedField]
        Pre-resolved field mappings
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
