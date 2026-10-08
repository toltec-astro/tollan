"""Tests for pandas DataFrame mapper implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from tollan.accessor.pandas import DataFrameMapper
from tollan.accessor.schema import NameMapping, Schema

if TYPE_CHECKING:
    from tollan.accessor.schema import Mapping


class TestDataFrameMapper:
    """Test DataFrameMapper for pandas.DataFrame."""

    def test_ambiguous_name_rejected(self):
        @dataclass
        class TestSchema(Schema):
            field: Mapping = NameMapping("field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        df = pd.DataFrame({"field": [1, 2]})
        df.attrs["field"] = "metadata"
        with pytest.raises(ValueError, match="Ambiguous field 'field'.*attr, var"):
            TestMapper.from_data_source(df)

    def test_column_location_does_not_switch_to_attribute(self):
        @dataclass
        class TestSchema(Schema):
            field: Mapping = NameMapping.var("field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        df = pd.DataFrame({"field": [1, 2]})
        df.attrs["field"] = "metadata"
        mapper = TestMapper.from_data_source(df)
        np.testing.assert_array_equal(mapper.get_value(df, mapper.schema.field), [1, 2])
        incompatible = pd.DataFrame()
        incompatible.attrs["field"] = "metadata"
        with pytest.raises(KeyError, match="field"):
            mapper.get_value(incompatible, mapper.schema.field)

    def test_unsupported_dimension_location(self):
        @dataclass
        class TestSchema(Schema):
            field: Mapping = NameMapping.dim("field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        with pytest.raises(ValueError, match="does not support location 'dim'"):
            TestMapper.from_data_source(pd.DataFrame({"field": [1, 2]}))

    def test_from_dataframe(self):
        """Create mapper from DataFrame."""
        df = pd.DataFrame({"temp": [25.0, 26.0], "pressure": [101.3, 101.4]})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")
            pressure: Mapping = NameMapping("pressure")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)

        assert isinstance(mapper, DataFrameMapper)

    def test_read_column_values(self):
        """Read column values as numpy arrays."""
        df = pd.DataFrame({"temp": [25.0, 26.0, 27.0]})

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temp")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.temp)

        assert isinstance(value, np.ndarray)
        np.testing.assert_array_equal(value, [25.0, 26.0, 27.0])

    def test_read_attrs(self):
        """Read values from DataFrame.attrs."""
        df = pd.DataFrame({"col": [1, 2]})
        df.attrs["metadata_field"] = "metadata_value"

        @dataclass
        class TestSchema(Schema):
            meta: Mapping = NameMapping("metadata_field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.meta)

        assert value == "metadata_value"

    def test_explicit_attribute_with_same_named_column(self):
        """The schema chooses which namespace to read."""
        df = pd.DataFrame({"field": [1, 2, 3]})
        df.attrs["field"] = "from_attrs"

        @dataclass
        class TestSchema(Schema):
            field: Mapping = NameMapping.attr("field")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)
        value = mapper.get_value(df, mapper.schema.field)

        # The column is not part of this mapping.
        assert value == "from_attrs"

    def test_missing_field(self):
        """Missing field raises KeyError."""
        df = pd.DataFrame({"temp": [25.0]})

        @dataclass
        class TestSchema(Schema):
            pressure: Mapping = NameMapping("pressure")

        class TestMapper(DataFrameMapper[TestSchema]):
            pass

        mapper = TestMapper.from_data_source(df)

        with pytest.raises(KeyError, match="Field not found"):
            mapper.get_value(df, mapper.schema.pressure)
