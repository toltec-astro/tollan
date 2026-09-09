"""netCDF4 Dataset-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..mapper import Mapper
from ..schema import Mapping, Schema

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
        """Check if a global attribute, variable, or dimension exists."""
        return (
            name in data_source.ncattrs()
            or name in data_source.variables
            or name in data_source.dimensions
        )

    def _read_value(self, data_source: nc.Dataset, name: str) -> Any:
        """Read field value from dataset.

        Global attributes take precedence over variables with the same name.
        Variable reads retain netCDF4's native masking and scaling behavior.
        Dimensions are returned as their current integer length.
        """
        if name in data_source.ncattrs():
            return data_source.getncattr(name)
        if name in data_source.variables:
            return data_source.variables[name][...]
        if name in data_source.dimensions:
            return len(data_source.dimensions[name])
        msg = f"Field {name} not found in dataset"
        raise KeyError(msg)

    def has_dim(self, data_source: nc.Dataset, field: Mapping) -> bool:
        """Return whether the mapped field names a NetCDF dimension."""
        name = self.get_name(field)
        return name is not None and name in data_source.dimensions

    def get_dim(self, data_source: nc.Dataset, field: Mapping) -> int:
        """Return the current length of a mapped NetCDF dimension."""
        name = self.get_name(field)
        if name is None or name not in data_source.dimensions:
            msg = f"Dimension not found: {field}"
            raise KeyError(msg)
        return len(data_source.dimensions[name])
