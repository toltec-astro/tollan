"""Minimal units accessor for xarray DataArrays using Astropy.

This module provides a lightweight xarray accessor for storing and retrieving
physical units on DataArrays. Units are stored in the DataArray's .attrs["units"]
dictionary and validated/converted using Astropy's units framework.

Features:
    - Store units on DataArrays via .attrs["units"]
    - Retrieve and validate unit strings
    - Convert between compatible units
    - Create Astropy Quantity objects
    - Simple, non-intrusive design with lazy evaluation

Example:
    >>> import xarray as xr
    >>>
    >>> # The accessor is registered automatically on import
    >>> da = xr.DataArray([1, 2, 3])
    >>>
    >>> # Set units
    >>> da_km = da.u.set("km")
    >>>
    >>> # Convert units (lazy evaluation with dask)
    >>> da_m = da_km.u.to("m")
    >>> print(da_m.values)
    [1000. 2000. 3000.]
    >>>
    >>> # Get Astropy Quantity
    >>> qty = da_km.u.quantity
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import xarray as xr
from astropy import units as astropy_units
from astropy.units import Quantity

if TYPE_CHECKING:
    from astropy.units import Unit

__all__ = [
    "UnitsAccessor",
]


@xr.register_dataarray_accessor("u")
class UnitsAccessor:
    """Accessor for unit handling on xarray DataArrays.

    Provides properties and methods for setting, getting, and converting physical
    units using Astropy's units framework. Units are stored in .attrs["units"]
    as strings. Registered as the 'u' accessor on DataArrays.

    Attributes
    ----------
    _obj : xr.DataArray
        The DataArray this accessor is attached to

    Properties
    ----------
    unit_str : str or None
        The unit string from .attrs["units"], or None if not set
    unit : astropy.units.Unit or None
        The Astropy Unit object, or None if not set
    quantity : astropy.units.Quantity
        The data as an Astropy Quantity object (converts to numpy array)

    Methods
    -------
    set(unit)
        Set units (only if not already set or same unit)
    unset()
        Remove units
    to(target_unit, equivalencies=None)
        Convert to different units (lazy evaluation preserved)

    Examples
    --------
    Set units on a DataArray:

        >>> da = xr.DataArray([1, 2, 3])
        >>> da_km = da.u.set("km")
        >>> print(da_km.attrs["units"])
        km

    Convert to different units:

        >>> da_m = da_km.u.to("m")
        >>> print(da_m.values)
        [1000. 2000. 3000.]

    Access as Astropy Quantity:

        >>> qty = da_km.u.quantity
        >>> print(qty)
        [1. 2. 3.] km
    """

    def __init__(self, xarray_obj: xr.DataArray) -> None:
        """Initialize the units accessor.

        Parameters
        ----------
        xarray_obj : xr.DataArray
            The DataArray to attach the accessor to
        """
        self._obj = xarray_obj

    @property
    def unit_str(self) -> str | None:
        """Get the unit string from the DataArray.

        Returns
        -------
        str or None
            The unit string if present, None otherwise

        Examples
        --------
        >>> da = xr.DataArray([1, 2, 3])
        >>> da.attrs["units"] = "km"
        >>> da.u.unit_str
        'km'
        >>> xr.DataArray([1, 2, 3]).u.unit_str is None
        True
        """
        return self._obj.attrs.get("units", None)

    @property
    def unit(self) -> Unit | None:
        """Get the Astropy Unit object from the DataArray.

        Returns
        -------
        astropy.units.Unit or None
            The Astropy Unit object if units are present and valid, None otherwise

        Raises
        ------
        ValueError
            If the unit string is present but invalid (raised by astropy)

        Examples
        --------
        >>> da = xr.DataArray([1, 2, 3])
        >>> da.attrs["units"] = "km"
        >>> unit = da.u.unit
        >>> print(unit)
        km
        >>> from astropy.units import UnitBase
        >>> isinstance(unit, UnitBase)
        True
        """
        unit_str = self.unit_str
        if unit_str is None:
            return None

        return astropy_units.Unit(unit_str)

    @property
    def quantity(self) -> Quantity:
        """Get the data as an Astropy Quantity object.

        If no units are set, returns the underlying DataArray directly.
        Uses the << operator to attach units without data copying.

        Returns
        -------
        astropy.units.Quantity or xr.DataArray
            Quantity object with data values and units, or the DataArray if no units

        Examples
        --------
        >>> da = xr.DataArray([1, 2, 3])
        >>> da_km = da.u.set("km")
        >>> qty = da_km.u.quantity
        >>> print(qty)
        [1. 2. 3.] km

        Without units, returns the DataArray:

        >>> da = xr.DataArray([1, 2, 3])
        >>> da.u.quantity is da
        True
        """
        unit = self.unit
        if unit is None:
            return self._obj  # type: ignore[return-value]

        # Use << operator to attach units without copying
        return self._obj.data << unit

    def set(self, unit: str | Unit) -> xr.DataArray:
        """Set units on the DataArray.

        Only sets units if:
        - No units are currently set, OR
        - The current units are the same as the new units (no-op)

        Raises an error if trying to set different units when units already exist.
        Use .u.unset() first to change units, or use .u.to() to convert.

        Parameters
        ----------
        unit : str or astropy.units.Unit
            Unit to set. If a string, will be validated as an Astropy unit.

        Returns
        -------
        xr.DataArray
            DataArray with units set in .attrs["units"], or self if no-op

        Raises
        ------
        ValueError
            If the unit string is invalid, or if trying to set different units
            when units already exist

        Examples
        --------
        Set units on a DataArray without units:

        >>> da = xr.DataArray([1, 2, 3])
        >>> da_km = da.u.set("km")
        >>> print(da_km.attrs["units"])
        km

        Setting same units is a no-op:

        >>> da_km2 = da_km.u.set("km")
        >>> da_km2 is da_km
        True

        Cannot set different units when units exist:

        >>> da_km.u.set("m")  # doctest: +SKIP
        ValueError: Cannot set different unit 'm' when unit 'km' already exists.
        Use .u.unset() first or .u.to('m') to convert.

        Set with Astropy Unit object:

        >>> from astropy import units as u
        >>> da_m = da.u.set(u.m)
        >>> print(da_m.attrs["units"])
        m
        """
        # Convert Astropy Unit to string (let astropy validate)
        if isinstance(unit, astropy_units.UnitBase):
            unit_str = str(unit)
        else:
            # Let astropy validate - it will raise if invalid
            unit_str = str(astropy_units.Unit(unit))

        # Check current units
        current_unit_str = self.unit_str

        if current_unit_str is None:
            # No units set - set them (assign_attrs creates shallow copy)
            return self._obj.assign_attrs(units=unit_str)
        if current_unit_str == unit_str:
            # Same units - no-op
            return self._obj
        # Different units already exist - error
        msg = (
            f"Cannot set different unit '{unit_str}' when unit "
            f"'{current_unit_str}' already exists. "
            f"Use .u.unset() first or .u.to('{unit_str}') to convert."
        )
        raise ValueError(msg)

    def unset(self) -> xr.DataArray:
        """Remove units from the DataArray.

        Does not modify data values, only removes the units attribute.

        Returns
        -------
        xr.DataArray
            DataArray with units removed from .attrs

        Examples
        --------
        >>> da = xr.DataArray([1, 2, 3])
        >>> da.attrs["units"] = "km"
        >>> da_no_units = da.u.unset()
        >>> "units" in da_no_units.attrs
        False
        """
        result = self._obj.copy(data=self._obj.data)
        result.attrs.pop("units", None)
        return result

    def to(
        self,
        target_unit: str | Unit,
        equivalencies: list | None = None,
    ) -> xr.DataArray:
        """Convert DataArray to different units.

        Converts both the data values and the units attribute. Preserves lazy
        evaluation when working with Dask arrays.

        Parameters
        ----------
        target_unit : str or astropy.units.Unit
            Target unit to convert to
        equivalencies : list, optional
            Astropy equivalencies to allow non-standard conversions
            (e.g., spectral equivalencies for frequency <-> wavelength)

        Returns
        -------
        xr.DataArray
            DataArray with converted values and units. If the input uses Dask
            arrays, the output will also use Dask arrays (lazy evaluation).

        Raises
        ------
        ValueError
            If DataArray has no units, or units are incompatible

        Examples
        --------
        Convert kilometers to meters:

        >>> da = xr.DataArray([1, 2, 3])
        >>> da_km = da.u.set("km")
        >>> da_m = da_km.u.to("m")
        >>> print(da_m.values)
        [1000. 2000. 3000.]
        >>> print(da_m.attrs["units"])
        m

        Use equivalencies for frequency <-> wavelength:

        >>> from astropy.units import spectral
        >>> da_freq = xr.DataArray([1e11, 2e11]).u.set("Hz")
        >>> da_wl = da_freq.u.to("mm", equivalencies=spectral())

        Lazy evaluation is preserved when working with Dask arrays.
        """
        current_unit = self.unit
        if current_unit is None:
            msg = "Cannot convert DataArray without units. Use .u.set() first."
            raise ValueError(msg)

        # Parse target unit
        if isinstance(target_unit, str):
            target_unit = astropy_units.Unit(target_unit)

        # Define conversion function for map_blocks
        def convert(data):
            quantity = Quantity(data, current_unit, copy=False)
            converted = quantity.to(target_unit, equivalencies=equivalencies)
            return converted.value

        # Apply conversion using map_blocks (preserves dask arrays)
        converted = xr.apply_ufunc(
            convert,
            self._obj,
            dask="parallelized",
            output_dtypes=[self._obj.dtype],
        )

        return converted.assign_attrs(units=str(target_unit))

    def __repr__(self) -> str:
        unit_display = self.unit_str if self.unit_str is not None else "no units"
        return f"UnitsAccessor({unit_display})"
