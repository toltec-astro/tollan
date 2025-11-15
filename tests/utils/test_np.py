"""Tests for NumPy utilities."""

from __future__ import annotations

import astropy.units as u
import numpy as np
import pytest

from tollan.utils.np import (
    attach_unit,
    ensure_unit,
    flex_reshape,
    make_complex,
    preserve_unit,
    qrange,
    strip_unit,
)


class TestFlexReshape:
    """Tests for flex_reshape function."""

    def test_basic_reshape_with_trim_end(self):
        """Test basic reshape with trimming from end."""
        arr = np.arange(10)
        result = flex_reshape(arr, (2, 4))
        expected = np.array([[0, 1, 2, 3], [4, 5, 6, 7]])
        np.testing.assert_array_equal(result, expected)

    def test_basic_reshape_with_trim_start(self):
        """Test basic reshape with trimming from start."""
        arr = np.arange(10)
        result = flex_reshape(arr, (2, 4), trim_option="start")
        expected = np.array([[2, 3, 4, 5], [6, 7, 8, 9]])
        np.testing.assert_array_equal(result, expected)

    def test_auto_dimension(self):
        """Test automatic dimension calculation with -1."""
        arr = np.arange(10)
        result = flex_reshape(arr, (2, -1))
        expected = np.array([[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]])
        np.testing.assert_array_equal(result, expected)

    def test_multiple_auto_dimensions_raises(self):
        """Test that multiple -1 dimensions raise error."""
        arr = np.arange(10)
        with pytest.raises(ValueError, match="only one dim can be -1"):
            flex_reshape(arr, (-1, -1))

    def test_invalid_trim_option_raises(self):
        """Test that invalid trim option raises error."""
        arr = np.arange(10)
        with pytest.raises(ValueError, match="invalid trim option"):
            flex_reshape(arr, (2, 4), trim_option="invalid")  # type: ignore[arg-type]


class TestMakeComplex:
    """Tests for make_complex function."""

    def test_basic_complex_creation(self):
        """Test basic complex array creation."""
        real = np.array([1.0, 2.0, 3.0])
        imag = np.array([4.0, 5.0, 6.0])
        result = make_complex(real, imag)
        expected = np.array([1 + 4j, 2 + 5j, 3 + 6j])
        np.testing.assert_array_equal(result, expected)

    def test_different_shapes_raises(self):
        """Test that different shapes raise error."""
        real = np.array([1.0, 2.0])
        imag = np.array([3.0, 4.0, 5.0])
        with pytest.raises(
            ValueError,
            match="real and imaginary parts have to be of the same shape",
        ):
            make_complex(real, imag)

    def test_multidimensional_arrays(self):
        """Test with multidimensional arrays."""
        real = np.array([[1.0, 2.0], [3.0, 4.0]])
        imag = np.array([[5.0, 6.0], [7.0, 8.0]])
        result = make_complex(real, imag)
        expected = np.array([[1 + 5j, 2 + 6j], [3 + 7j, 4 + 8j]])
        np.testing.assert_array_equal(result, expected)


class TestStripUnit:
    """Tests for strip_unit function."""

    def test_strip_from_quantity(self):
        """Test stripping unit from Quantity."""
        arr = np.array([1, 2, 3]) << u.m  # type: ignore[attr-defined]
        data, unit = strip_unit(arr)
        np.testing.assert_array_equal(data, np.array([1, 2, 3]))
        assert unit == u.m  # type: ignore[attr-defined]

    def test_strip_from_plain_array(self):
        """Test with plain array (no unit)."""
        arr = np.array([1, 2, 3])
        data, unit = strip_unit(arr)  # type: ignore[arg-type]
        np.testing.assert_array_equal(data, arr)
        assert unit is None

    def test_strip_from_masked_quantity(self):
        """Test with masked array with units."""
        data_arr = np.array([1, 2, 3]) << u.m  # type: ignore[attr-defined]
        arr = np.ma.array(data_arr, mask=[False, True, False])
        data, unit = strip_unit(arr)
        np.testing.assert_array_equal(data.data, np.array([1, 2, 3]))  # type: ignore[union-attr]
        assert unit == u.m  # type: ignore[attr-defined]

    def test_strip_from_masked_array_no_unit(self):
        """Test with masked array without units."""
        arr = np.ma.array([1, 2, 3], mask=[False, True, False])
        data, unit = strip_unit(arr)
        assert isinstance(data, np.ma.MaskedArray)
        assert unit is None


class TestAttachUnit:
    """Tests for attach_unit function."""

    def test_attach_to_plain_array(self):
        """Test attaching unit to plain array."""
        arr = np.array([1, 2, 3])
        result = attach_unit(arr, u.m)  # type: ignore[attr-defined]
        assert isinstance(result, u.Quantity)
        assert result.unit == u.m  # type: ignore[attr-defined]
        np.testing.assert_array_equal(result.value, arr)

    def test_attach_none_returns_original(self):
        """Test that attaching None returns original array."""
        arr = np.array([1, 2, 3])
        result = attach_unit(arr, None)
        np.testing.assert_array_equal(result, arr)

    def test_attach_to_masked_array(self):
        """Test attaching unit to masked array."""
        arr = np.ma.array([1, 2, 3], mask=[False, True, False])
        result = attach_unit(arr, u.m)  # type: ignore[attr-defined]
        assert isinstance(result.data, u.Quantity)  # type: ignore[union-attr]
        assert result.data.unit == u.m  # type: ignore[attr-defined, union-attr]
        assert isinstance(result, np.ma.MaskedArray)
        assert result.data.unit == u.m  # type: ignore[attr-defined, union-attr]


class TestPreserveUnit:
    """Tests for preserve_unit decorator."""

    def test_preserves_unit(self):
        """Test that decorator preserves units."""

        @preserve_unit
        def double(x):
            return x * 2

        arr = np.array([1, 2, 3]) << u.m  # type: ignore[attr-defined]
        result = double(arr)
        assert isinstance(result, u.Quantity)
        assert result.unit == u.m  # type: ignore[attr-defined]
        np.testing.assert_array_equal(result.value, np.array([2, 4, 6]))

    def test_works_without_unit(self):
        """Test decorator works with plain arrays."""

        @preserve_unit
        def double(x):
            return x * 2

        arr = np.array([1, 2, 3])
        result = double(arr)
        np.testing.assert_array_equal(result, np.array([2, 4, 6]))

    def test_with_additional_args(self):
        """Test decorator with additional arguments."""

        @preserve_unit
        def multiply(x, factor, offset=0):
            return x * factor + offset

        arr = np.array([1, 2, 3]) << u.m  # type: ignore[attr-defined]
        result = multiply(arr, 2, offset=1)
        assert result.unit == u.m  # type: ignore[attr-defined]
        np.testing.assert_array_equal(result.value, np.array([3, 5, 7]))


class TestEnsureUnit:
    """Tests for ensure_unit function."""

    def test_attach_unit_to_plain_array(self):
        """Test attaching unit to plain array."""
        arr = np.array([1, 2, 3])
        result = ensure_unit(arr, u.m)  # type: ignore[attr-defined]
        assert isinstance(result, u.Quantity)
        assert result.unit == u.m  # type: ignore[attr-defined]

    def test_convert_existing_unit(self):
        """Test converting existing unit."""
        arr = np.array([100, 200, 300]) << u.cm  # type: ignore[attr-defined]
        result = ensure_unit(arr, u.m)  # type: ignore[attr-defined]
        assert result.unit == u.m  # type: ignore[attr-defined, union-attr]
        np.testing.assert_allclose(result.value, np.array([1, 2, 3]))  # type: ignore[union-attr]

    def test_none_returns_none(self):
        """Test that None returns None."""
        result = ensure_unit(None, u.m)  # type: ignore[attr-defined]
        assert result is None


class TestQrange:
    """Tests for qrange function."""

    def test_basic_range(self):
        """Test basic quantity range."""
        result = qrange(0 * u.m, 10 * u.m, 2 * u.m)  # type: ignore[attr-defined]
        expected = np.array([0, 2, 4, 6, 8]) << u.m  # type: ignore[attr-defined]
        assert result.unit == u.m  # type: ignore[attr-defined]
        np.testing.assert_array_equal(result.value, expected.value)

    def test_frequency_range(self):
        """Test with frequency units."""
        result = qrange(0 * u.Hz, 1 * u.kHz, 250 * u.Hz)  # type: ignore[attr-defined]
        expected = np.array([0, 250, 500, 750]) << u.Hz  # type: ignore[attr-defined]
        assert result.unit == u.Hz  # type: ignore[attr-defined]
        np.testing.assert_array_equal(result.value, expected.value)

    def test_fractional_step(self):
        """Test with fractional step size."""
        result = qrange(0 * u.m, 1 * u.m, 0.25 * u.m)  # type: ignore[attr-defined]
        expected = np.array([0, 0.25, 0.5, 0.75]) << u.m  # type: ignore[attr-defined]
        np.testing.assert_allclose(result.value, expected.value)
