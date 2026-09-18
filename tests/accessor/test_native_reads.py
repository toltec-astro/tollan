"""Native-variable lookup and shared scalar/text reads across backends."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_type

import dask.array as da
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from dask import delayed

from tollan.accessor import NameMapping, Schema
from tollan.accessor.netcdf4 import NetCDF4Mapper
from tollan.accessor.pandas import DataFrameMapper
from tollan.accessor.xarray import XarrayMapper

if TYPE_CHECKING:
    from tollan.accessor import Mapping
    from tollan.accessor.xarray.units import QDataArray

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="numpy.ndarray size changed")
    import netCDF4 as nc  # noqa: N813


@dataclass
class ReadingsSchema(Schema):
    signal: Mapping = NameMapping.var("signal")
    count: Mapping = NameMapping.var("count")
    text: Mapping = NameMapping.var("text")
    chars: Mapping = NameMapping.var("chars")
    label: Mapping = NameMapping.attr("label")
    missing: Mapping = NameMapping.var("missing")


class ArrayMapper(XarrayMapper[ReadingsSchema]):
    pass


class FileMapper(NetCDF4Mapper[ReadingsSchema]):
    pass


class TableMapper(DataFrameMapper[ReadingsSchema]):
    pass


@pytest.fixture(params=["xarray", "netcdf4", "pandas"])
def native_case(request, tmp_path):
    kind = request.param
    if kind == "xarray":
        source = xr.Dataset(
            {
                "signal": ("sample", [1, 2, 3]),
                "count": xr.DataArray(42),
                "text": xr.DataArray(b" hello "),
                "chars": ("char", np.array(list("hello"), dtype="S1")),
            },
            attrs={"label": " hello "},
        )
        yield kind, source, ArrayMapper.from_data_source(source)
    elif kind == "pandas":
        source = pd.DataFrame(
            {"signal": [1, 2, 3], "count": [42, 42, 42], "text": ["hello"] * 3},
            index=[10, 20, 30],
        )
        source.attrs["label"] = " hello "
        yield kind, source, TableMapper.from_data_source(source)
    else:
        with nc.Dataset(tmp_path / "readings.nc", "w") as source:
            source.createDimension("sample", 3)
            source.createDimension("char", 5)
            source.createVariable("signal", "i4", ("sample",))[:] = [1, 2, 3]
            source.createVariable("count", "i4")[...] = 42
            source.createVariable("text", str)[...] = " hello "
            source.createVariable("chars", "S1", ("char",))[:] = np.array(
                list("hello"), dtype="S1"
            )
            source.setncattr("label", " hello ")
            yield kind, source, FileMapper.from_data_source(source)


def test_native_variable_does_not_read_values(native_case, monkeypatch):
    kind, source, mapper = native_case

    def unexpected_read(var):
        pytest.fail("Native lookup must not materialize values")

    monkeypatch.setattr(mapper, "_read_var_values", unexpected_read)
    field = mapper.schema.signal
    assert mapper.has_var(source, field)
    assert not mapper.has_var(source, mapper.schema.label)
    variable = mapper.get_var(source, field)
    if kind == "xarray":
        assert isinstance(variable, xr.DataArray)
        assert variable.identical(source["signal"])
    elif kind == "pandas":
        assert isinstance(variable, pd.Series)
        assert variable.index.tolist() == [10, 20, 30]
        assert variable.equals(source["signal"])
    else:
        assert variable is source.variables["signal"]


def test_backend_aliases_use_the_shared_implementation(native_case):
    kind, source, mapper = native_case
    suffix = {"xarray": "arr", "netcdf4": "var", "pandas": "col"}[kind]
    get_native = getattr(mapper, f"get_{suffix}")
    has_native = getattr(mapper, f"has_{suffix}")
    assert get_native.__func__ is mapper.get_var.__func__
    assert has_native.__func__ is mapper.has_var.__func__
    assert has_native(source, mapper.schema.signal)
    assert not has_native(source, mapper.schema.label)
    assert not has_native(source, mapper.schema.missing)
    variable = get_native(source, mapper.schema.signal)
    if kind == "xarray":
        assert variable.identical(source["signal"])
    elif kind == "pandas":
        assert variable.equals(source["signal"])
    else:
        assert variable is source.variables["signal"]
    with pytest.raises(KeyError):
        get_native(source, mapper.schema.missing)
    with pytest.raises(ValueError):
        get_native(source, mapper.schema.label)


@pytest.mark.parametrize("method", ["get_value", "get_value_or_default"])
def test_value_read_looks_up_and_materializes_once(native_case, monkeypatch, method):
    _, source, mapper = native_case
    get_var = mapper._get_var
    read_values = mapper._read_var_values
    events = []

    def get(source, name):
        var = get_var(source, name)
        events.append(("get", var))
        return var

    def read(var):
        events.append(("read", var))
        return read_values(var)

    monkeypatch.setattr(mapper, "_get_var", get)
    monkeypatch.setattr(mapper, "_read_var_values", read)
    np.testing.assert_array_equal(
        getattr(mapper, method)(source, mapper.schema.signal), [1, 2, 3]
    )
    assert [action for action, _ in events] == ["get", "read"]
    assert events[0][1] is events[1][1]


def test_shared_attribute_scalar_and_string_reads(native_case):
    _, source, mapper = native_case
    assert mapper.get_scalar(source, mapper.schema.label) == " hello "
    assert mapper.get_str(source, mapper.schema.label) == "hello"
    assert not mapper.has_var(source, mapper.schema.label)


@pytest.mark.parametrize("method", ["get_scalar", "get_str"])
def test_invalid_variable_rejected_before_read(native_case, monkeypatch, method):
    _, source, mapper = native_case
    mapper = type(mapper).from_data_source(source, {mapper.schema.signal: "fallback"})

    def unexpected_read(var):
        pytest.fail("Reject unsuitable variable metadata before loading values")

    monkeypatch.setattr(mapper, "_read_var_values", unexpected_read)
    with pytest.raises(ValueError):
        getattr(mapper, method)(source, mapper.schema.signal)


def test_scalar_and_string_variable_reads(native_case):
    kind, source, mapper = native_case
    if kind == "pandas":
        for current in (source, source.iloc[:1]):
            with pytest.raises(ValueError, match="cannot be read as a scalar"):
                mapper.get_scalar(current, mapper.schema.count)
            with pytest.raises(ValueError, match="cannot be read as a single string"):
                mapper.get_str(current, mapper.schema.text)
    else:
        assert mapper.get_scalar(source, mapper.schema.count) == 42
        assert mapper.get_str(source, mapper.schema.text) == "hello"
        assert mapper.get_str(source, mapper.schema.chars) == "hello"


def test_string_defaults_and_native_reads_are_distinct(native_case):
    _, source, mapper = native_case
    field = mapper.schema.missing
    mapper = type(mapper).from_data_source(source, {field: b" default\x00 "})
    assert mapper.get_value_or_default(source, field) == b" default\x00 "
    with pytest.raises(KeyError):
        mapper.get_value(source, field)
    with pytest.raises(KeyError):
        mapper.get_str(source, field)
    assert not mapper.has_var(source, field)
    with pytest.raises(KeyError):
        mapper.get_var(source, field)
    with pytest.raises(KeyError):
        mapper.get_scalar(source, field)


def test_defaults_follow_current_attribute_presence(native_case):
    kind, source, mapper = native_case
    field = mapper.schema.label
    mapper = type(mapper).from_data_source(source, {field: "fallback"})
    assert mapper.get_value_or_default(source, field) == " hello "
    if kind == "netcdf4":
        source.delncattr("label")
        lookup_error = AttributeError
    else:
        del source.attrs["label"]
        lookup_error = KeyError
    assert mapper.get_value_or_default(source, field) == "fallback"
    for method in ("get_value", "get_scalar", "get_str"):
        with pytest.raises(lookup_error):
            getattr(mapper, method)(source, field)

    mapper = type(mapper).from_data_source(source, {field: "fallback"})
    if kind == "netcdf4":
        source.setncattr("label", " present ")
    else:
        source.attrs["label"] = " present "
    assert mapper.get_value_or_default(source, field) == " present "
    assert mapper.get_value(source, field) == " present "
    assert mapper.get_scalar(source, field) == " present "
    assert mapper.get_str(source, field) == "present"


@pytest.mark.parametrize(
    ("shape", "dtype", "error"),
    [
        ((4,), "S8", ValueError),
        ((4,), object, ValueError),
        ((4,), float, ValueError),
        ((2, 2), "S1", ValueError),
        ((), float, TypeError),
        ((1,), float, TypeError),
    ],
)
def test_xarray_string_rejects_invalid_metadata_without_compute(shape, dtype, error):
    @delayed
    def values():
        pytest.fail("Invalid string metadata must be rejected before computation")

    source = xr.Dataset(
        {"text": xr.DataArray(da.from_delayed(values(), shape=shape, dtype=dtype))}
    )
    mapper = ArrayMapper.from_data_source(source)
    with pytest.raises(error, match="not a single string"):
        mapper.get_str(source, mapper.schema.text)


def test_xarray_valid_string_computes_once():
    computed = []

    @delayed
    def values():
        computed.append(True)
        return np.array(list("hello"), dtype="S1")

    source = xr.Dataset(
        {"chars": ("char", da.from_delayed(values(), shape=(5,), dtype="S1"))}
    )
    mapper = ArrayMapper.from_data_source(source)
    assert computed == []
    assert mapper.get_str(source, mapper.schema.chars) == "hello"
    assert computed == [True]


def test_netcdf_null_padded_character_string(tmp_path):
    with nc.Dataset(tmp_path / "readings.nc", "w") as source:
        source.createDimension("char", 8)
        chars = source.createVariable("chars", "S1", ("char",))
        chars[:] = np.frombuffer(b" hello\x00\x00", dtype="S1")
        mapper = FileMapper.from_data_source(source)
        # Native netCDF reads mask null fill characters, including text padding.
        assert mapper.get_str(source, mapper.schema.chars) == "hello"


# netCDF4's character decoder still assigns ndarray.shape under NumPy 2.5.
@pytest.mark.filterwarnings(
    "ignore:Setting the shape on a NumPy array has been deprecated:DeprecationWarning"
)
def test_netcdf_scalar_mask_and_string_encoding(tmp_path):
    with nc.Dataset(tmp_path / "readings.nc", "w") as source:
        source.createVariable("count", "i4", fill_value=-99)[...] = -99
        source.createDimension("char", 4)
        chars = source.createVariable("chars", "S1", ("char",))
        chars[:] = np.frombuffer("café".encode("latin-1"), dtype="S1")
        chars.setncattr("_Encoding", "latin-1")
        mapper = FileMapper.from_data_source(source)
        assert mapper.get_scalar(source, mapper.schema.count) is np.ma.masked
        # netCDF4 may already decode character arrays through _Encoding.
        assert mapper.get_str(source, mapper.schema.chars, encoding="latin-1") == "café"


def test_native_return_types(tmp_path):
    array = xr.Dataset({"signal": ("sample", [1, 2])})
    array_mapper = ArrayMapper.from_data_source(array)
    if TYPE_CHECKING:
        assert_type(array_mapper.get_var(array, array_mapper.schema.signal), QDataArray)
        assert_type(array_mapper.get_arr(array, array_mapper.schema.signal), QDataArray)
    assert_type(array_mapper.has_var(array, array_mapper.schema.signal), bool)
    assert_type(array_mapper.has_arr(array, array_mapper.schema.signal), bool)

    frame = pd.DataFrame({"signal": [1, 2]})
    table_mapper = TableMapper.from_data_source(frame)
    assert_type(table_mapper.get_var(frame, table_mapper.schema.signal), pd.Series)
    assert_type(table_mapper.get_col(frame, table_mapper.schema.signal), pd.Series)
    assert_type(table_mapper.has_var(frame, table_mapper.schema.signal), bool)
    assert_type(table_mapper.has_col(frame, table_mapper.schema.signal), bool)

    with nc.Dataset(tmp_path / "readings.nc", "w") as source:
        source.createVariable("signal", "i4")[...] = 1
        file_mapper = FileMapper.from_data_source(source)
        assert_type(file_mapper.get_var(source, file_mapper.schema.signal), nc.Variable)
        assert_type(file_mapper.has_var(source, file_mapper.schema.signal), bool)
