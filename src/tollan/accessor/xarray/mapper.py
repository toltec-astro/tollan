"""Xarray-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import xarray as xr
from astropy import units as astropy_units

if TYPE_CHECKING:
    from astropy.units import PhysicalType

    from .units import QDataArray
    from .utils import XarraySourceT

from ..mapper import Mapper
from ..schema import Mapping, NameMapping, Schema
from .utils import unwrap_data_source

__all__ = ["XarrayMapper"]

_NOT_FOUND = object()


class XarrayMapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for xarray data sources.

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
    ...     time: Mapping = NameMapping("time")
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

    @classmethod
    def _find_arr(
        cls,
        data_source: XarraySourceT,
        name: str,
    ) -> xr.DataArray | None:
        """Find an array payload or coordinate without reading its values."""
        array_source = unwrap_data_source(data_source)
        if isinstance(array_source, xr.Dataset):
            if name in array_source.data_vars or name in array_source.coords:
                return array_source[name]
            return None

        # unwrap_data_source() leaves only xr.DataArray in this branch.
        payload_name = array_source.name or "data"
        if name == payload_name:
            return array_source
        if name in array_source.coords:
            return array_source.coords[name]
        return None

    @classmethod
    def _find_attr(
        cls,
        data_source: XarraySourceT,
        name: str,
    ) -> Any:
        """Return an attribute value, or a private sentinel when absent."""
        return unwrap_data_source(data_source).attrs.get(name, _NOT_FOUND)

    def _has_field(self, data_source: XarraySourceT, name: str) -> bool:
        """Check if field exists as data variable, coordinate, or attribute."""
        if self._find_attr(data_source, name) is not _NOT_FOUND:
            return True
        return self._find_arr(data_source, name) is not None

    def _read_value(self, data_source: XarraySourceT, name: str) -> Any:
        """Read a backend-free field value from an xarray source.

        Attributes take precedence over arrays with the same name. Array reads
        explicitly materialize through :meth:`xarray.DataArray.to_numpy`.
        """
        attr = self._find_attr(data_source, name)
        if attr is not _NOT_FOUND:
            return attr
        arr = self._find_arr(data_source, name)
        if arr is None:
            raise KeyError(name)
        return arr.to_numpy()

    def has_arr(self, data_source: XarraySourceT, field: Mapping) -> bool:
        """Check if field exists as a data variable or coordinate.

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to check
        field : Mapping
            Field mapping from schema

        Returns
        -------
        bool
            True if field exists as a data variable or coordinate in dataset

        """
        name = self.get_name(field)
        if name is None:
            return False
        return self._find_arr(data_source, name) is not None

    def has_attr(self, data_source: XarraySourceT, field: Mapping) -> bool:
        """Check if field exists as an attribute.

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to check
        field : Mapping
            Field mapping from schema

        Returns
        -------
        bool
            True if field exists as an attribute in dataset
        """
        name = self.get_name(field)
        if name is None:
            return False
        return self._find_attr(data_source, name) is not _NOT_FOUND

    def get_arr(self, data_source: XarraySourceT, field: Mapping) -> QDataArray:
        """Get DataArray for a schema field.

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to read from
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
        name = self.get_name(field)
        arr = None if name is None else self._find_arr(data_source, name)
        if arr is None:
            field_name = name if name is not None else field
            msg = (
                f"Field {field_name!r} not found as an array in "
                f"{type(data_source).__name__}"
            )
            raise ValueError(msg)
        return cast("QDataArray", arr)

    def get_scalar(self, data_source: XarraySourceT, field: Mapping) -> Any:
        """Get scalar value for a schema field.

        Retrieves scalar values from attributes or 0-D arrays. This is useful
        for metadata fields.

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to read from
        field : Mapping
            Field mapping from schema

        Returns
        -------
        scalar
            Scalar value from dataset or attrs

        Raises
        ------
        ValueError
            If field not found in dataset or is not a scalar (ndim != 0)
        """
        name = self.get_name(field)
        if name is None:
            msg = f"Field mapping {field!r} is not available in this mapper"
            raise ValueError(msg)

        attr = self._find_attr(data_source, name)
        if attr is not _NOT_FOUND:
            return attr

        arr = self._find_arr(data_source, name)
        if arr is None:
            msg = f"Field {name!r} not found in {type(data_source).__name__}"
            raise ValueError(msg)
        if arr.ndim == 0 or (arr.dtype.kind in ("U", "S", "O") and arr.size == 1):
            return arr.to_numpy().item()
        msg = f"Field {name!r} is not a scalar (ndim=0)"
        raise ValueError(msg)

    def get_shape(self, data_source: XarraySourceT, field: Mapping) -> tuple[int, ...]:
        """Get shape of a field's data array.

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to inspect
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

    def validate_has_field(self, field: Mapping) -> None:
        """Validate that a required field was found during mapping.

        This checks the concrete plan resolved from the mapper's reference
        source. It does not inspect the source supplied to a later read.

        Parameters
        ----------
        field : Mapping
            Field mapping to validate

        Raises
        ------
        ValueError
            If field is missing from the schema mapping
        """
        if field not in self:
            field_name = self.get_name(field)
            if field_name is None and isinstance(field, NameMapping):
                field_name = field.names[0]
            if field_name is None:
                field_name = field
            msg = f"Missing required field {field_name!r}"
            raise ValueError(msg)

    def validate_ndim(
        self,
        data_source: XarraySourceT,
        field: Mapping,
        expected_ndim: int,
    ) -> None:
        """Validate that a field has the expected number of dimensions.

        This is essential for ensuring data has the correct shape for
        operations like sweeps (2-D) or timestreams (1-D or 2-D).

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to validate
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
        data_source: XarraySourceT,
        field: Mapping,
        expected_physical_type: str | PhysicalType,
    ) -> None:
        """Validate that a field has the expected physical type.

        Uses the units accessor to check the physical type of the field's units
        via astropy. This ensures dimensional consistency (e.g., frequency data
        has frequency units like Hz or GHz, not time units).

        Parameters
        ----------
        data_source : XarraySourceT
            Dataset, DataArray, or DataTree current node to validate
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
