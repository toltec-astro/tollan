"""Tests for tollan.accessor.units - minimal units accessor for xarray."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from astropy import units as u
from astropy.units import Quantity

from tollan.accessor.units import UnitsAccessor


class TestUnitsAccessor:
    """Test UnitsAccessor registration and basic functionality."""

    def test_accessor_registration(self):
        """Test that units accessor is registered on DataArray."""
        da = xr.DataArray([1, 2, 3])
        assert hasattr(da, "u")
        assert isinstance(da.u, UnitsAccessor)

    def test_unit_str_no_units(self):
        """Test unit_str property returns None when no units are set."""
        da = xr.DataArray([1, 2, 3])
        assert da.u.unit_str is None

    def test_unit_str_with_units(self):
        """Test unit_str property returns unit string when units are set."""
        da = xr.DataArray([1, 2, 3])
        da.attrs["units"] = "km"
        assert da.u.unit_str == "km"

    def test_unit_no_units(self):
        """Test unit property returns None when no units."""
        da = xr.DataArray([1, 2, 3])
        assert da.u.unit is None

    def test_unit_with_units(self):
        """Test unit property returns Astropy Unit when units are set."""
        da = xr.DataArray([1, 2, 3])
        da.attrs["units"] = "m"
        assert da.u.unit == u.m
        assert isinstance(da.u.unit, u.UnitBase)


class TestSetUnits:
    """Test setting units on DataArrays."""

    def test_set_units_string(self):
        """Test setting units with a string."""
        da = xr.DataArray([1, 2, 3])
        da_with_units = da.u.set("km")

        assert da_with_units.attrs["units"] == "km"
        # Original should be unchanged
        assert "units" not in da.attrs

    def test_set_units_astropy_unit(self):
        """Test setting units with Astropy Unit object."""
        da = xr.DataArray([1, 2, 3])
        da_with_units = da.u.set(u.m)

        assert da_with_units.attrs["units"] == "m"

    def test_set_invalid_units(self):
        """Test setting invalid units raises ValueError."""
        da = xr.DataArray([1, 2, 3])

        with pytest.raises(ValueError):
            da.u.set("not_a_unit")

    def test_set_units_preserves_data(self):
        """Test that setting units doesn't modify data values."""
        da = xr.DataArray([1, 2, 3])
        da_with_units = da.u.set("km")

        np.testing.assert_array_equal(da_with_units.values, da.values)

    def test_set_same_units_is_noop(self):
        """Test setting same units is a no-op."""
        da = xr.DataArray([1, 2, 3])
        da_km = da.u.set("km")
        da_km2 = da_km.u.set("km")

        assert da_km2 is da_km

    def test_set_different_units_fails(self):
        """Test setting different units when units exist raises error."""
        da = xr.DataArray([1, 2, 3])
        da_km = da.u.set("km")

        with pytest.raises(ValueError, match="Cannot set different unit"):
            da_km.u.set("m")

    def test_unset_units(self):
        """Test removing units from DataArray."""
        da = xr.DataArray([1, 2, 3])
        da.attrs["units"] = "km"

        da_no_units = da.u.unset()

        assert "units" not in da_no_units.attrs
        assert da.attrs["units"] == "km"  # Original unchanged

    def test_set_preserves_data_reference(self):
        """Test that setting units creates shallow copy (same .data reference)."""
        da = xr.DataArray([1, 2, 3])
        da_km = da.u.set("km")

        # Should be shallow copy - same underlying data
        assert da_km.data is da.data

    def test_unset_preserves_data_reference(self):
        """Test that unsetting units creates shallow copy (same .data reference)."""
        da = xr.DataArray([1, 2, 3])
        da.attrs["units"] = "km"
        da_no_units = da.u.unset()

        # Should be shallow copy - same underlying data
        assert da_no_units.data is da.data


class TestQuantityProperty:
    """Test quantity property for Astropy Quantity objects."""

    def test_quantity_no_units(self):
        """Test quantity returns DataArray when no units."""
        da = xr.DataArray([1, 2, 3])
        assert da.u.quantity is da

    def test_quantity_with_units(self):
        """Test quantity returns Astropy Quantity object."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_km = da.u.set("km")

        qty = da_km.u.quantity
        assert isinstance(qty, Quantity)
        assert qty.unit == u.km
        np.testing.assert_array_equal(qty.value, [1.0, 2.0, 3.0])

    def test_quantity_invalid_units(self):
        """Test quantity raises ValueError for invalid unit string."""
        da = xr.DataArray([1, 2, 3])
        da.attrs["units"] = "invalid_unit"

        with pytest.raises(ValueError):
            _ = da.u.quantity


class TestUnitConversion:
    """Test unit conversion functionality."""

    def test_convert_length_units(self):
        """Test converting between length units."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_km = da.u.set("km")

        da_m = da_km.u.to("m")

        assert da_m.attrs["units"] == "m"
        np.testing.assert_allclose(da_m.values, [1000.0, 2000.0, 3000.0])

    def test_convert_frequency_units(self):
        """Test converting between frequency units."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_ghz = da.u.set("GHz")

        da_hz = da_ghz.u.to("Hz")

        assert da_hz.attrs["units"] == "Hz"
        np.testing.assert_allclose(da_hz.values, [1e9, 2e9, 3e9])

    def test_convert_time_units(self):
        """Test converting between time units."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_s = da.u.set("s")

        da_ms = da_s.u.to("ms")

        assert da_ms.attrs["units"] == "ms"
        np.testing.assert_allclose(da_ms.values, [1000.0, 2000.0, 3000.0])

    def test_convert_without_units_fails(self):
        """Test conversion fails if no units are set."""
        da = xr.DataArray([1.0, 2.0, 3.0])

        with pytest.raises(ValueError, match="Cannot convert DataArray without units"):
            da.u.to("m")

    def test_convert_incompatible_units_fails(self):
        """Test conversion fails for incompatible units."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_km = da.u.set("km")

        with pytest.raises(u.UnitConversionError):
            da_km.u.to("s")

    def test_convert_with_astropy_unit_object(self):
        """Test conversion using Astropy Unit object as target."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_km = da.u.set("km")

        da_m = da_km.u.to(u.m)

        assert da_m.attrs["units"] == "m"
        np.testing.assert_allclose(da_m.values, [1000.0, 2000.0, 3000.0])


class TestDaskSupport:
    """Test lazy evaluation with Dask arrays."""

    def test_set_preserves_dask(self):
        """Test that setting units preserves Dask arrays."""
        import dask.array as da

        dask_data = da.from_array(
            np.array([1.0, 2.0, 3.0]),
            chunks=2,  # pyright: ignore[reportArgumentType]
        )
        xda = xr.DataArray(dask_data)
        xda_km = xda.u.set("km")

        assert isinstance(xda_km.data, da.Array)

    def test_to_preserves_dask(self):
        """Test that to() preserves lazy evaluation with Dask."""
        import dask.array as da

        dask_data = da.from_array(
            np.array([1.0, 2.0, 3.0]),
            chunks=2,  # pyright: ignore[reportArgumentType]
        )
        xda = xr.DataArray(dask_data)
        xda_km = xda.u.set("km")
        xda_m = xda_km.u.to("m")

        # Should still be lazy
        assert isinstance(xda_m.data, da.Array)

        # Compute and verify values
        computed = xda_m.compute()
        np.testing.assert_allclose(computed.values, [1000.0, 2000.0, 3000.0])


class TestAstropyEquivalencies:
    """Test Astropy equivalencies for non-standard conversions."""

    def test_spectral_equivalency(self):
        """Test spectral equivalency for frequency <-> wavelength."""
        from astropy.units import spectral

        # Create frequency DataArray
        da_freq = xr.DataArray([1e11, 2e11, 3e11])
        da_freq = da_freq.u.set("Hz")

        # Convert using equivalencies
        da_wl = da_freq.u.to("mm", equivalencies=spectral())

        # Verify conversion: lambda = c / nu
        c = 299792458.0  # m/s
        expected_m = c / da_freq.values
        expected_mm = expected_m * 1000

        np.testing.assert_allclose(da_wl.values, expected_mm, rtol=1e-6)
        assert da_wl.attrs["units"] == "mm"


class TestStringRepresentation:
    """Test string representations of the accessor."""

    def test_repr_with_units(self):
        """Test __repr__ with units set."""
        da = xr.DataArray([1, 2, 3])
        da_km = da.u.set("km")

        assert repr(da_km.u) == "UnitsAccessor(km)"

    def test_repr_no_units(self):
        """Test __repr__ without units."""
        da = xr.DataArray([1, 2, 3])

        assert repr(da.u) == "UnitsAccessor(no units)"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_multidimensional_array(self):
        """Test units work with multi-dimensional arrays."""
        da = xr.DataArray(np.ones((3, 4, 5)))
        da_km = da.u.set("km")
        da_m = da_km.u.to("m")

        assert da_m.shape == (3, 4, 5)
        np.testing.assert_allclose(da_m.values, np.ones((3, 4, 5)) * 1000)

    def test_preserves_coordinates(self):
        """Test that unit operations preserve coordinates."""
        da = xr.DataArray(
            [1.0, 2.0, 3.0],
            coords={"x": [0, 1, 2]},
            dims=["x"],
        )
        da_km = da.u.set("km")
        da_m = da_km.u.to("m")

        assert "x" in da_m.coords
        np.testing.assert_array_equal(da_m.coords["x"].values, [0, 1, 2])

    def test_preserves_other_attrs(self):
        """Test that unit operations preserve other attributes."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da.attrs["description"] = "test data"
        da.attrs["source"] = "experiment"

        da_km = da.u.set("km")
        da_m = da_km.u.to("m")

        assert da_m.attrs["description"] == "test data"
        assert da_m.attrs["source"] == "experiment"

    def test_compound_units(self):
        """Test compound units like m/s."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_ms = da.u.set("m/s")

        # Astropy may format with or without spaces
        assert "m" in da_ms.attrs["units"] and "s" in da_ms.attrs["units"]

        da_kms = da_ms.u.to("km/s")
        np.testing.assert_allclose(da_kms.values, [0.001, 0.002, 0.003])

    def test_dimensionless_units(self):
        """Test dimensionless units."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_dimless = da.u.set("")

        assert da_dimless.attrs["units"] == ""

    def test_chained_conversions(self):
        """Test multiple consecutive conversions."""
        da = xr.DataArray([1.0])
        da_km = da.u.set("km")
        da_m = da_km.u.to("m")
        da_cm = da_m.u.to("cm")
        da_mm = da_cm.u.to("mm")

        assert da_mm.attrs["units"] == "mm"
        np.testing.assert_allclose(da_mm.values, [1e6])


class TestIntegrationWithXarray:
    """Test integration with xarray operations."""

    def test_units_survive_selection(self):
        """Test that units are preserved with .sel()."""
        da = xr.DataArray(
            [1.0, 2.0, 3.0],
            coords={"x": [0, 1, 2]},
            dims=["x"],
        )
        da_km = da.u.set("km")

        selected = da_km.sel(x=1)

        assert selected.attrs["units"] == "km"

    def test_units_survive_copy(self):
        """Test that units are preserved with .copy()."""
        da = xr.DataArray([1.0, 2.0, 3.0])
        da_km = da.u.set("km")

        copied = da_km.copy()

        assert copied.attrs["units"] == "km"

    def test_dataset_coord_units(self):
        """Test setting units on dataset coordinates."""
        ds = xr.Dataset({"data": (["x"], [1, 2, 3])})
        ds = ds.assign_coords(x=xr.DataArray([0, 1, 2]).u.set("m"))

        assert ds.coords["x"].attrs["units"] == "m"

        # Convert coordinate units
        ds_km = ds.assign_coords(x=ds.coords["x"].u.to("km"))

        assert ds_km.coords["x"].attrs["units"] == "km"
        np.testing.assert_allclose(ds_km.coords["x"].values, [0, 0.001, 0.002])
