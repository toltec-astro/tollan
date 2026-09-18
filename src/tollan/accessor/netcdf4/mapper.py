"""netCDF4 Dataset-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from ..mapper import Mapper
from ..schema import FieldLocation, Schema

if TYPE_CHECKING:
    import netCDF4 as nc  # noqa: N813


__all__ = ["NetCDF4Mapper"]


class NetCDF4Mapper[SchemaT: Schema = Schema](
    Mapper[SchemaT, "nc.Dataset", "nc.Variable"]
):
    """Mapper for netCDF4.Dataset.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)
    """

    _supported_locations: ClassVar = tuple(FieldLocation)

    def _has_attr(self, data_source: nc.Dataset, name: str) -> bool:
        """Check global attribute names without reading values."""
        return name in data_source.ncattrs()

    def _has_var(self, data_source: nc.Dataset, name: str) -> bool:
        """Check variable names without reading values."""
        return name in data_source.variables

    def _has_dim(self, data_source: nc.Dataset, name: str) -> bool:
        """Check dimension names without reading arrays."""
        return name in data_source.dimensions

    def _get_attr(self, data_source: nc.Dataset, name: str) -> Any:
        """Return a global attribute through the netCDF attribute API."""
        return data_source.getncattr(name)

    def _get_var(self, data_source: nc.Dataset, name: str) -> nc.Variable:
        """Return a native Variable without loading its values."""
        return data_source.variables[name]

    def _read_var_values(self, var: nc.Variable) -> Any:
        """Read variable values with native netCDF masking and scaling."""
        return var[...]

    def _get_dim(self, data_source: nc.Dataset, name: str) -> int:
        """Return a dimension's current length without reading its coordinate."""
        return len(data_source.dimensions[name])

    def _read_scalar_var(self, var: nc.Variable) -> Any:
        """Read a 0-D or single-element string variable, preserving missing values."""
        if var.ndim == 0 or (
            np.dtype(var.dtype).kind in ("U", "S", "O") and var.size == 1
        ):
            value = self._read_var_values(var)
            if np.ma.is_masked(value):
                return np.ma.masked
            return np.asanyarray(value).item()
        msg = f"Field {var.name!r} is not a scalar (ndim=0)"
        raise ValueError(msg)

    def _read_str_var(self, var: nc.Variable) -> Any:
        """Read one string or character array after checking shape and dtype."""
        dtype = np.dtype(var.dtype)
        if not (
            var.ndim == 0
            or (var.ndim == 1 and (var.size == 1 or dtype in ("S1", "U1")))
        ):
            msg = f"Field {var.name!r} is not a single string"
            raise ValueError(msg)
        if dtype.kind not in ("U", "S", "O"):
            msg = f"Field {var.name!r} is not a single string"
            raise TypeError(msg)
        return self._read_var_values(var)
