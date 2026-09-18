"""Xarray-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import xarray as xr
from astropy import units as astropy_units

if TYPE_CHECKING:
    import numpy as np
    from astropy.units import PhysicalType

    from ..schema import Mapping
    from .units import QDataArray

from ..mapper import Mapper
from ..schema import FieldLocation, Schema
from .utils import XarrayPayloadT

__all__ = ["XarrayMapper"]


class XarrayMapper[SchemaT: Schema = Schema](
    Mapper[SchemaT, XarrayPayloadT, "QDataArray"]
):
    """Mapper for xarray data sources.

    Use get_arr() and has_arr() as aliases for get_var() and
    has_var(). Array reads return native DataArrays without loading values.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper

    Examples
    --------
    >>> import xarray as xr
    >>> from dataclasses import dataclass
    >>> from tollan.accessor.schema import Mapping, NameMapping, Schema
    >>>
    >>> @dataclass
    ... class MySchema(Schema):
    ...     temperature: Mapping = NameMapping("temp")
    ...     time: Mapping = NameMapping.var("time")
    >>>
    >>> class MyMapper(XarrayMapper[MySchema]):
    ...     pass
    >>>
    >>> ds = xr.Dataset(
    ...     {"temp": (["time"], [20.0, 21.0, 22.0])},
    ...     coords={"time": [0, 1, 2]}
    ... )
    >>> mapper = MyMapper.from_data_source(ds)
    >>> mapper.get_value(ds, mapper.schema.temperature)
    array([20., 21., 22.])
    """

    _supported_locations: ClassVar = tuple(FieldLocation)

    get_arr = Mapper[SchemaT, XarrayPayloadT, "QDataArray"].get_var
    has_arr = Mapper[SchemaT, XarrayPayloadT, "QDataArray"].has_var

    @classmethod
    def from_data_source(
        cls,
        data_source: XarrayPayloadT | None,
        defaults: dict[Mapping, Any] | None = None,
    ) -> Self:
        """Resolve fields against an unwrapped Dataset or DataArray payload.

        Accessors select DataTree nodes and unwrap DataArray containers before
        calling this method. None constructs a defaults-only mapper.
        """
        if data_source is not None and not isinstance(
            data_source, xr.Dataset | xr.DataArray
        ):
            msg = (
                "Expected a Dataset or DataArray payload; "
                "select or unwrap the source first"
            )
            raise TypeError(msg)
        return super().from_data_source(data_source, defaults)

    def _has_attr(self, data_source: XarrayPayloadT, name: str) -> bool:
        """Check source attributes without reading values."""
        return name in data_source.attrs

    def _has_var(self, data_source: XarrayPayloadT, name: str) -> bool:
        """Check variables or coordinates without reading values."""
        if isinstance(data_source, xr.Dataset):
            return name in data_source.variables
        return name == (data_source.name or "data") or name in data_source.coords

    def _has_dim(self, data_source: XarrayPayloadT, name: str) -> bool:
        """Check dimension names without reading array values."""
        return name in data_source.sizes

    def _get_attr(self, data_source: XarrayPayloadT, name: str) -> Any:
        """Return a source attribute unchanged."""
        return data_source.attrs[name]

    def _read_var_values(self, var: QDataArray) -> np.ndarray:
        """Read variable values as a NumPy array, computing lazy data if needed."""
        return var.to_numpy()

    def _get_dim(self, data_source: XarrayPayloadT, name: str) -> int:
        """Return a dimension's current length without reading its coordinate."""
        return data_source.sizes[name]

    def _get_var(self, data_source: XarrayPayloadT, name: str) -> QDataArray:
        """Return the native variable or coordinate without loading values."""
        if isinstance(data_source, xr.Dataset):
            # Dataset indexing alone can synthesize a coordinate for a bare dim.
            if name not in data_source.variables:
                raise KeyError(name)
            return cast("QDataArray", data_source[name])
        # The remaining payload type is DataArray.
        if name == (data_source.name or "data"):
            return cast("QDataArray", data_source)
        return cast("QDataArray", data_source.coords[name])

    def _read_scalar_var(self, var: QDataArray) -> Any:
        """Read a 0-D or single-element string variable as a scalar."""
        if var.ndim == 0 or (var.dtype.kind in ("U", "S", "O") and var.size == 1):
            return self._read_var_values(var).item()
        msg = f"Field {var.name!r} is not a scalar (ndim=0)"
        raise ValueError(msg)

    def _read_str_var(self, var: QDataArray) -> Any:
        """Read one string or character array after checking shape and dtype."""
        if not (
            var.ndim == 0
            or (var.ndim == 1 and (var.size == 1 or var.dtype in ("S1", "U1")))
        ):
            msg = f"Field {var.name!r} is not a single string"
            raise ValueError(msg)
        if var.dtype.kind not in ("U", "S", "O"):
            msg = f"Field {var.name!r} is not a single string"
            raise TypeError(msg)
        return self._read_var_values(var)

    def get_shape(self, data_source: XarrayPayloadT, field: Mapping) -> tuple[int, ...]:
        """Get shape of a field's data array.

        Parameters
        ----------
        data_source : XarrayPayloadT
            Unwrapped Dataset or DataArray payload to inspect
        field : Mapping
            Field mapping from schema

        Returns
        -------
        tuple[int, ...]
            Shape of the data array as (dim1_size, dim2_size, ...)

        Raises
        ------
        ValueError
            If field not found in dataset
        """
        arr = self.get_arr(data_source, field)
        return arr.shape

    def validate_ndim(
        self,
        data_source: XarrayPayloadT,
        field: Mapping,
        expected_ndim: int,
    ) -> None:
        """Validate that a field has the expected number of dimensions.

        This is essential for ensuring data has the correct shape for
        operations like sweeps (2-D) or timestreams (1-D or 2-D).

        Parameters
        ----------
        data_source : XarrayPayloadT
            Unwrapped Dataset or DataArray payload to validate
        field : Mapping
            Field mapping to validate
        expected_ndim : int
            Expected number of dimensions (1 for 1-D, 2 for 2-D, etc.)

        Raises
        ------
        ValueError
            If field has wrong dimensionality
        """
        shape = self.get_shape(data_source, field)
        actual_ndim = len(shape)
        if actual_ndim != expected_ndim:
            field_name = self.get_name(field)
            msg = f"Field '{field_name}' must be {expected_ndim}-D, got {actual_ndim}-D"
            raise ValueError(msg)

    def validate_has_physical_type(
        self,
        data_source: XarrayPayloadT,
        field: Mapping,
        expected_physical_type: str | PhysicalType,
    ) -> None:
        """Validate that a field has the expected physical type.

        Uses the units accessor to check the physical type of the field's units
        via astropy. This ensures dimensional consistency (e.g., frequency data
        has frequency units like Hz or GHz, not time units).

        Parameters
        ----------
        data_source : XarrayPayloadT
            Unwrapped Dataset or DataArray payload to validate
        field : Mapping
            Field mapping to validate
        expected_physical_type : str or astropy.units.PhysicalType
            Expected physical type (e.g., 'frequency', 'time', 'length')

        Raises
        ------
        ValueError
            If field has no units or wrong physical type

        Notes
        -----
        The field must have a 'units' attribute that can be parsed by astropy.
        Common physical types include 'frequency', 'time', 'length', 'angle',
        'temperature', etc.
        """
        physical_type_expected = astropy_units.get_physical_type(
            expected_physical_type,
        )
        field_name = self.get_name(field)
        da = self.get_arr(data_source, field)
        unit = da.u.unit

        if unit is None:
            msg = f"Field '{field_name}' has no units set"
            raise ValueError(msg)

        physical_type_actual = unit.physical_type
        if physical_type_actual != physical_type_expected:
            msg = (
                f"Field '{field_name}' has physical type '{physical_type_actual}', "
                f"expected '{physical_type_expected}'"
            )
            raise ValueError(msg)
