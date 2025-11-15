"""Tests for table validation utilities."""

from __future__ import annotations

import pandas as pd
import pytest
from astropy.table import QTable, Table

from tollan.utils.table import TableValidator


@pytest.fixture
def validator():
    """Create a TableValidator instance."""
    return TableValidator()


@pytest.fixture
def astro_table():
    """Create sample astropy Table."""
    return Table(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        names=["a", "b", "c"],
        meta={"key1": "value1", "key2": "value2"},
    )


@pytest.fixture
def pandas_table():
    """Create sample pandas DataFrame."""
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6], "z": [7, 8, 9]})
    df.attrs = {"key1": "value1", "key2": "value2"}
    return df


class TestColumnValidation:
    """Test column validation methods."""

    def test_validate_cols_astropy(self, validator, astro_table):
        """Test validate_cols with astropy Table."""
        result = validator.validate_cols(astro_table, ["a", "b", "nonexistent"])
        assert result == ["a", "b"]

    def test_validate_cols_pandas(self, validator, pandas_table):
        """Test validate_cols with pandas DataFrame."""
        result = validator.validate_cols(pandas_table, ["x", "z", "missing"])
        assert result == ["x", "z"]

    def test_has_any_col_true(self, validator, astro_table):
        """Test has_any_col returns True when at least one col exists."""
        assert validator.has_any_col(astro_table, ["a", "missing"])

    def test_has_any_col_false(self, validator, astro_table):
        """Test has_any_col returns False when no cols exist."""
        assert not validator.has_any_col(astro_table, ["missing1", "missing2"])

    def test_has_all_cols_true(self, validator, pandas_table):
        """Test has_all_cols returns True when all cols exist."""
        assert validator.has_all_cols(pandas_table, ["x", "y", "z"])

    def test_has_all_cols_false(self, validator, pandas_table):
        """Test has_all_cols returns False when not all cols exist."""
        assert not validator.has_all_cols(pandas_table, ["x", "y", "missing"])

    def test_get_first_col_found(self, validator, astro_table):
        """Test get_first_col returns first existing column."""
        result = validator.get_first_col(astro_table, ["missing", "b", "a"])
        assert result == "b"

    def test_get_first_col_not_found(self, validator, astro_table):
        """Test get_first_col returns None when no column exists."""
        result = validator.get_first_col(astro_table, ["missing1", "missing2"])
        assert result is None


class TestColumnData:
    """Test column data retrieval methods."""

    def test_get_first_col_data_found(self, validator, astro_table):
        """Test get_first_col_data returns column data."""
        result = validator.get_first_col_data(astro_table, ["missing", "b", "a"])
        assert list(result) == [4, 5, 6]

    def test_get_first_col_data_not_found(self, validator, astro_table):
        """Test get_first_col_data returns None when no column exists."""
        result = validator.get_first_col_data(astro_table, ["missing1", "missing2"])
        assert result is None

    def test_get_col_data_mixed(self, validator, pandas_table):
        """Test get_col_data with mix of existing and missing columns."""
        result = validator.get_col_data(pandas_table, ["x", "missing", "z"])
        assert len(result) == 3
        assert list(result[0]) == [1, 2, 3]
        assert result[1] is None
        assert list(result[2]) == [7, 8, 9]

    def test_get_col_data_all_missing(self, validator, pandas_table):
        """Test get_col_data with all missing columns."""
        result = validator.get_col_data(pandas_table, ["missing1", "missing2"])
        assert result == [None, None]


class TestMetadataValidation:
    """Test metadata validation methods."""

    def test_validate_meta(self, validator):
        """Test validate_meta returns existing keys."""
        meta = {"a": 1, "b": 2, "c": 3}
        result = validator.validate_meta(meta, ["a", "b", "missing"])
        assert result == ["a", "b"]

    def test_has_any_meta_true(self, validator):
        """Test has_any_meta returns True when at least one key exists."""
        meta = {"a": 1, "b": 2}
        assert validator.has_any_meta(meta, ["a", "missing"])

    def test_has_any_meta_false(self, validator):
        """Test has_any_meta returns False when no keys exist."""
        meta = {"a": 1, "b": 2}
        assert not validator.has_any_meta(meta, ["missing1", "missing2"])

    def test_has_all_meta_true(self, validator):
        """Test has_all_meta returns True when all keys exist."""
        meta = {"a": 1, "b": 2, "c": 3}
        assert validator.has_all_meta(meta, ["a", "b", "c"])

    def test_has_all_meta_false(self, validator):
        """Test has_all_meta returns False when not all keys exist."""
        meta = {"a": 1, "b": 2}
        assert not validator.has_all_meta(meta, ["a", "b", "missing"])

    def test_get_first_meta_found(self, validator):
        """Test get_first_meta returns first existing key."""
        meta = {"a": 1, "b": 2}
        result = validator.get_first_meta(meta, ["missing", "b", "a"])
        assert result == "b"

    def test_get_first_meta_not_found(self, validator):
        """Test get_first_meta returns None when no key exists."""
        meta = {"a": 1, "b": 2}
        result = validator.get_first_meta(meta, ["missing1", "missing2"])
        assert result is None


class TestMetadataValues:
    """Test metadata value retrieval methods."""

    def test_get_first_meta_value_found(self, validator):
        """Test get_first_meta_value returns value for first existing key."""
        meta = {"a": 10, "b": 20}
        result = validator.get_first_meta_value(meta, ["missing", "b", "a"])
        assert result == 20

    def test_get_first_meta_value_not_found(self, validator):
        """Test get_first_meta_value returns None when no key exists."""
        meta = {"a": 10, "b": 20}
        result = validator.get_first_meta_value(meta, ["missing1", "missing2"])
        assert result is None

    def test_get_meta_values_mixed(self, validator):
        """Test get_meta_values with mix of existing and missing keys."""
        meta = {"a": 10, "b": 20, "c": 30}
        result = validator.get_meta_values(meta, ["a", "missing", "c"])
        assert result == [10, None, 30]

    def test_get_meta_values_all_missing(self, validator):
        """Test get_meta_values with all missing keys."""
        meta = {"a": 10, "b": 20}
        result = validator.get_meta_values(meta, ["missing1", "missing2"])
        assert result == [None, None]


class TestExpressionEvaluation:
    """Test expression evaluation methods."""

    def test_eval_astropy_table(self, validator, astro_table):
        """Test eval with astropy Table."""
        result = validator.eval(astro_table, "a + b")
        assert list(result) == [5, 7, 9]

    def test_eval_pandas_dataframe(self, validator, pandas_table):
        """Test eval with pandas DataFrame."""
        result = validator.eval(pandas_table, "x * y")
        assert list(result) == [4, 10, 18]

    def test_query_astropy_table(self, validator, astro_table):
        """Test query with astropy Table."""
        result = validator.query(astro_table, "a > 1")
        assert len(result) == 2
        assert list(result["a"]) == [2, 3]

    def test_query_pandas_dataframe(self, validator, pandas_table):
        """Test query with pandas DataFrame."""
        result = validator.query(pandas_table, "x > 1")
        assert len(result) == 2
        assert list(result["x"]) == [2, 3]

    def test_eval_with_custom_local_dict(self, validator, astro_table):
        """Test eval with custom local_dict for astropy Table."""
        result = validator.eval(
            astro_table,
            "a + custom_var",
            local_dict={"custom_var": 10},
        )
        assert list(result) == [11, 12, 13]


class TestQTable:
    """Test with astropy QTable."""

    def test_qtable_column_validation(self, validator):
        """Test column validation works with QTable."""
        import astropy.units as u

        qtbl = QTable([[1, 2, 3] * u.m, [4, 5, 6] * u.s], names=["distance", "time"])  # type: ignore[attr-defined]
        assert validator.has_all_cols(qtbl, ["distance", "time"])
        assert validator.get_first_col(qtbl, ["time", "distance"]) == "time"

    def test_qtable_eval(self, validator):
        """Test eval works with QTable."""
        import astropy.units as u

        qtbl = QTable([[1, 2, 3] * u.m, [4, 5, 6] * u.s], names=["distance", "time"])  # type: ignore[attr-defined]
        # Note: This will strip units when using pd.eval
        result = validator.eval(qtbl, "distance.value + time.value")
        assert list(result) == [5, 7, 9]
