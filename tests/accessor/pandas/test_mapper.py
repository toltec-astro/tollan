"""Tests for pandas DataFrame mapper implementation."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
from pydantic.dataclasses import dataclass

from tollan.accessor.pandas import DataFrameMapper
from tollan.accessor.schema import Mapping, Schema

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="numpy.ndarray size changed",
        category=RuntimeWarning,
    )


class TestDataFrameMapper:
    """Test DataFrameMapper for pandas.DataFrame."""

    def test_from_dataframe(self):
        """Create mapper from DataFrame."""
        df = pd.DataFrame({"temp": [25.0, 26.0], "pressure": [101.3, 101.4]})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")
            pressure: Mapping = Mapping("pressure")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)

        assert isinstance(mapper, DataFrameMapper)

    def test_read_column_values(self):
        """Read column values as numpy arrays."""
        df = pd.DataFrame({"temp": [25.0, 26.0, 27.0]})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = Mapping("temp")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.temp)

        assert isinstance(value, np.ndarray)
        assert len(value) == 3
        assert value[0] == 25.0

    def test_read_attrs(self):
        """Read values from DataFrame.attrs."""
        df = pd.DataFrame({"col": [1, 2]})
        df.attrs["metadata_field"] = "metadata_value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = Mapping("metadata_field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.meta)

        assert value == "metadata_value"

    def test_attrs_priority_over_columns(self):
        """attrs take priority over columns with same name."""
        df = pd.DataFrame({"field": [1, 2, 3]})
        df.attrs["field"] = "from_attrs"

        @dataclass
        class TestSchema(Schema):
            field: Mapping = Mapping("field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.field)

        # attrs should be checked first
        assert value == "from_attrs"

    def test_missing_field(self):
        """Missing field raises KeyError."""
        df = pd.DataFrame({"temp": [25.0]})

        @dataclass
        class TestSchema(Schema):
            pressure: Mapping = Mapping("pressure")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)

        with pytest.raises(KeyError, match="Field not found"):
            mapper.get_value(df, mapper.schema.pressure)
