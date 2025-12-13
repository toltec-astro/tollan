"""Xarray-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xarray as xr

if TYPE_CHECKING:
    from ..schema import Mapping
    from ..units import QDataArray, QDataSourceT

    type DataSourceT = xr.Dataset | xr.DataArray | QDataSourceT

from ..mapper import Mapper
from ..schema import Schema

__all__ = ["XarrayMapper"]


class XarrayMapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for xarray.Dataset.

    This mapper provides a unified interface for accessing data from xarray
    Datasets, supporting data variables, coordinates, and attributes.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper

    Examples
    --------
    >>> import xarray as xr
    >>> from dataclasses import dataclass
    >>> from tollan.accessor.schema import Schema, Mapping
    >>>
    >>> @dataclass
    ... class MySchema(Schema):
    ...     temperature: Mapping = Mapping("temp")
    ...     time: Mapping = Mapping("time")
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

    def _has_field(self, data_source: DataSourceT, name: str) -> bool:
        """Check if field exists as data variable, coordinate, or attribute."""
        return (
            name in data_source.data_vars
            or name in data_source.coords
            or name in data_source.attrs
        )

    def _read_value(self, data_source: DataSourceT, name: str) -> Any:
        """Read field value from dataset.

        Returns the underlying numpy array for data variables/coords,
        or the raw attribute value for attributes.
        """
        if name in data_source.attrs:
            return data_source.attrs[name]
        return data_source[name].values  # ty: ignore[invalid-argument-type]

    def has_arr(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Check if field exists as a data variable or coordinate.

        Parameters
        ----------
        data_source : DataSourceT
            Dataset or DataArray to check
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
        return name in data_source

    def has_attr(self, data_source: DataSourceT, field: Mapping) -> bool:
        """Check if field exists as an attribute.

        Parameters
        ----------
        data_source : DataSourceT
            Dataset or DataArray to check
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
        return name in data_source.attrs

    def get_arr(self, data_source: DataSourceT, field: Mapping) -> QDataArray:
        """Get DataArray for a schema field.

        Parameters
        ----------
        data_source : DataSourceT
            Dataset or DataArray to read from
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

        # Handle Dataset vs DataArray differently
        if isinstance(data_source, xr.Dataset):
            # For Dataset: check data_vars and coords using __contains__
            if name not in data_source:
                msg = f"Field '{field.names[0]}' not found in dataset"
                raise ValueError(msg)
            return data_source[name]  # pyright: ignore[reportReturnType]  # ty:ignore[invalid-return-type]
        assert isinstance(data_source, xr.DataArray)
        if name not in data_source.coords:
            msg = f"Field '{field.names[0]}' not found in data array coords"
            raise ValueError(msg)
        return data_source.coords[name]  # pyright: ignore[reportReturnType]

    def get_scalar(self, data_source: DataSourceT, field: Mapping) -> Any:
        """Get scalar value for a schema field.

        Retrieves scalar values from attributes or 0-D arrays. This is useful
        for metadata fields.

        Parameters
        ----------
        data_source : DataSourceT
            Dataset or DataArray to read from
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
        if field not in self:
            msg = f"Field '{field.names[0]}' not found in dataset"
            raise ValueError(msg)
        name = self.get_name(field)

        # Check if it's in attrs first
        if name in data_source.attrs:
            return data_source.attrs[name]

        # Check if it's a variable
        if name in data_source:
            var = data_source[name]  # ty: ignore[invalid-argument-type]
            # Only accept 0-D arrays (true scalars)
            if var.ndim == 0:
                return var.item()
            # Special case: 0-D string stored as variable
            # xarray sometimes stores scalar strings with ndim > 0
            if var.dtype.kind in ("U", "S", "O") and var.size == 1:
                return var.item()

        msg = f"Field '{field.names[0]}' is not a scalar (ndim=0)"
        raise ValueError(msg)

    def get_shape(self, data_source: DataSourceT, field: Mapping) -> tuple[int, ...]:
        """Get shape of a field's data array.

        Parameters
        ----------
        data_source : DataSourceT
            Dataset to read from
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
        """Validate that a required field exists in the mapped schema.

        This checks if the field is defined in the schema and has a valid
        mapping. It does not check if the field exists in a particular dataset.

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
            field_name = field.names[0]
            msg = f"Missing required field '{field_name}'"
            raise ValueError(msg)

    def validate_ndim(
        self,
        data_source: DataSourceT,
        field: Mapping,
        expected_ndim: int,
    ) -> None:
        """Validate that a field has the expected number of dimensions.

        This is essential for ensuring data has the correct shape for
        operations like sweeps (2-D) or timestreams (1-D or 2-D).

        Parameters
        ----------
        data_source : DataSourceT
            Dataset or DataArray to validate
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
        data_source: DataSourceT,
        field: Mapping,
        expected_physical_type: str,
    ) -> None:
        """Validate that a field has the expected physical type.

        Uses the units accessor to check the physical type of the field's units
        via astropy. This ensures dimensional consistency (e.g., frequency data
        has frequency units like Hz or GHz, not time units).

        Parameters
        ----------
        data_source : DataSourceT
            Dataset or DataArray to validate
        field : Mapping
            Field mapping to validate
        expected_physical_type : str
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
        field_name = self.get_name(field)
        da = self.get_arr(data_source, field)
        unit = da.u.unit

        if unit is None:
            msg = f"Field '{field_name}' has no units set"
            raise ValueError(msg)

        # Check physical type
        actual_physical_type = unit.physical_type
        if actual_physical_type != expected_physical_type:
            msg = (
                f"Field '{field_name}' has physical type '{actual_physical_type}', "
                f"expected '{expected_physical_type}'"
            )
            raise ValueError(msg)
