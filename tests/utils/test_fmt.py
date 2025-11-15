"""Tests for formatting utilities."""

from __future__ import annotations

from enum import Flag

import numpy as np
import pandas as pd
import pytest

from tollan.utils.fmt import (
    BitmaskStats,
    bitmask_stats,
    pformat_bitmask,
    pformat_fancy_index,
    pformat_mask,
    pformat_yaml,
)


class TestPformatYaml:
    """Test YAML formatting."""

    def test_simple_dict(self):
        """Test formatting simple dictionary."""
        data = {"a": 1, "b": 2}
        result = pformat_yaml(data)
        assert result.startswith("\n")
        assert "a: 1" in result
        assert "b: 2" in result

    def test_nested_dict(self):
        """Test formatting nested dictionary."""
        data = {"outer": {"inner": 42}}
        result = pformat_yaml(data)
        assert "outer" in result
        assert "inner" in result
        assert "42" in result

    def test_with_wrapped_attribute(self):
        """Test formatting object with __wrapped__ attribute."""

        class Wrapper:
            def __init__(self, obj):
                self.__wrapped__ = obj

        wrapped = Wrapper({"key": "value"})
        result = pformat_yaml(wrapped)
        assert "key" in result
        assert "value" in result

    def test_with_numpy_types(self):
        """Test formatting with numpy scalar types."""
        data = {
            "float64": np.float64(3.14),
            "float32": np.float32(2.71),
            "int32": np.int32(42),
            "int64": np.int64(100),
        }
        result = pformat_yaml(data)
        # Should handle numpy types without errors
        assert "float64" in result
        assert "int32" in result


class TestPformatFancyIndex:
    """Test fancy index formatting."""

    def test_slice_full(self):
        """Test formatting slice with all components."""
        result = pformat_fancy_index(slice(1, 10, 2))
        assert result == "[1:10:2]"

    def test_slice_step_one(self):
        """Test formatting slice with step=1."""
        result = pformat_fancy_index(slice(1, 10, 1))
        assert result == "[1:10]"

    def test_slice_no_step(self):
        """Test formatting slice with no step."""
        result = pformat_fancy_index(slice(1, 10))
        assert result == "[1:10]"

    def test_slice_no_start(self):
        """Test formatting slice with no start."""
        result = pformat_fancy_index(slice(None, 10))
        assert result == "[:10]"

    def test_slice_no_stop(self):
        """Test formatting slice with no stop."""
        result = pformat_fancy_index(slice(5, None))
        assert result == "[5:]"

    def test_slice_no_start_no_stop(self):
        """Test formatting slice with neither start nor stop."""
        result = pformat_fancy_index(slice(None, None, 2))
        assert result == "[::2]"

    def test_numpy_mask(self):
        """Test formatting numpy boolean mask."""
        mask = np.array([True, False, True, True, False])
        result = pformat_fancy_index(mask)
        assert result == "<mask 3/5>"

    def test_list_of_slices(self):
        """Test formatting list of slices."""
        indices = [slice(0, 2), slice(3, 5)]
        result = pformat_fancy_index(indices)
        assert result == "[[0:2], [3:5]]"

    def test_scalar_value(self):
        """Test formatting scalar value."""
        result = pformat_fancy_index(42)
        assert result == "42"


class TestPformatMask:
    """Test mask formatting."""

    def test_all_true(self):
        """Test formatting mask with all True values."""
        mask = np.array([True, True, True])
        result = pformat_mask(mask)
        assert result == "3/3 (100.00%)"

    def test_all_false(self):
        """Test formatting mask with all False values."""
        mask = np.array([False, False, False])
        result = pformat_mask(mask)
        assert result == "0/3 (0.00%)"

    def test_partial(self):
        """Test formatting mask with partial True values."""
        mask = np.array([True, False, True, False, False])
        result = pformat_mask(mask)
        assert result == "2/5 (40.00%)"

    def test_single_element(self):
        """Test formatting single-element mask."""
        mask = np.array([True])
        result = pformat_mask(mask)
        assert result == "1/1 (100.00%)"


class TestBitmaskStats:
    """Test bitmask statistics computation."""

    @pytest.fixture
    def sample_flag(self):
        """Create sample Flag class."""

        class Status(Flag):
            OK = 1
            WARNING = 2
            ERROR = 4

        return Status

    def test_bitmask_stats_function(self, sample_flag):
        """Test bitmask_stats function."""
        # Create bitmask: [OK, OK|WARNING, OK|ERROR, OK|WARNING|ERROR]
        bitmask = np.array([1, 3, 5, 7])
        stats = bitmask_stats(sample_flag, bitmask)

        assert isinstance(stats, pd.DataFrame)
        assert len(stats) == 3  # Three flags
        assert list(stats.columns) == ["name", "selected", "total", "frac", "summary"]

        # All items have OK flag
        ok_row = stats[stats["name"] == "OK"].iloc[0]
        assert ok_row["selected"] == 4
        assert ok_row["total"] == 4
        assert ok_row["frac"] == 1.0

        # Half have WARNING flag
        warning_row = stats[stats["name"] == "WARNING"].iloc[0]
        assert warning_row["selected"] == 2
        assert warning_row["total"] == 4
        assert warning_row["frac"] == 0.5

        # Half have ERROR flag
        error_row = stats[stats["name"] == "ERROR"].iloc[0]
        assert error_row["selected"] == 2
        assert error_row["total"] == 4
        assert error_row["frac"] == 0.5

    def test_bitmask_stats_class(self, sample_flag):
        """Test BitmaskStats class."""
        bitmask = np.array([1, 3, 5, 7])
        stats = BitmaskStats(sample_flag, bitmask)

        # Check stats property
        assert isinstance(stats.stats, pd.DataFrame)
        assert len(stats.stats) == 3

        # Check pformat method
        formatted = stats.pformat()
        assert "OK" in formatted
        assert "WARNING" in formatted
        assert "ERROR" in formatted
        assert "4/4 (100.00%)" in formatted
        assert "2/4 (50.00%)" in formatted

    def test_pformat_bitmask_function(self, sample_flag):
        """Test pformat_bitmask convenience function."""
        bitmask = np.array([1, 2, 4])
        result = pformat_bitmask(sample_flag, bitmask)

        assert isinstance(result, str)
        assert "OK" in result
        assert "WARNING" in result
        assert "ERROR" in result

    def test_no_flags_set(self, sample_flag):
        """Test with bitmask where no flags are set."""
        bitmask = np.array([0, 0, 0])
        stats = bitmask_stats(sample_flag, bitmask)

        for _, row in stats.iterrows():
            assert row["selected"] == 0
            assert row["total"] == 3
            assert row["frac"] == 0.0
            assert "0/3 (0.00%)" in row["summary"]

    def test_all_flags_set(self, sample_flag):
        """Test with bitmask where all flags are set."""
        bitmask = np.array([7, 7, 7])  # OK | WARNING | ERROR
        stats = bitmask_stats(sample_flag, bitmask)

        for _, row in stats.iterrows():
            assert row["selected"] == 3
            assert row["total"] == 3
            assert row["frac"] == 1.0
            assert "3/3 (100.00%)" in row["summary"]


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_bitmask(self):
        """Test with empty bitmask array."""

        class Status(Flag):
            OK = 1

        bitmask = np.array([], dtype=int)
        stats = bitmask_stats(Status, bitmask)

        assert len(stats) == 1
        ok_row = stats.iloc[0]
        assert ok_row["selected"] == 0
        assert ok_row["total"] == 0
        # Division by zero should result in nan
        assert np.isnan(ok_row["frac"])

    def test_single_flag(self):
        """Test with Flag class containing single flag."""

        class Single(Flag):
            ONLY = 1

        bitmask = np.array([1, 0, 1])
        stats = bitmask_stats(Single, bitmask)

        assert len(stats) == 1
        assert stats.iloc[0]["selected"] == 2
        assert stats.iloc[0]["total"] == 3

    def test_many_flags(self):
        """Test with Flag class containing many flags."""

        class ManyFlags(Flag):
            F1 = 1
            F2 = 2
            F3 = 4
            F4 = 8
            F5 = 16

        bitmask = np.array([31])  # All flags set
        stats = bitmask_stats(ManyFlags, bitmask)

        assert len(stats) == 5
        for _, row in stats.iterrows():
            assert row["selected"] == 1
            assert row["frac"] == 1.0
