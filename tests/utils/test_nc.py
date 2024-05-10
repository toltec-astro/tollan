import tempfile
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from tollan.utils.log import logger
from tollan.utils.nc import (
    NcNodeMapper,
    NcNodeMapperError,
    NcNodeMapperTree,
    ncinfo,
    ncopen,
    ncstr,
)


def _make_dataset(ncfile):
    ds = netCDF4.Dataset(ncfile, "w", format="NETCDF4")  # type: ignore
    ds.createDimension("time_len", None)
    ds.createDimension("value_len", 10)
    ds.createDimension("name_len", 128)
    v_time = ds.createVariable("time", "i4", ("time_len",))
    v_value = ds.createVariable("value", "f8", ("value_len",))
    v_name = ds.createVariable("name", "|S1", ("name_len",))
    v_scalar = ds.createVariable("scalar", "f8", ())
    v_time[:] = np.arange(3)
    v_value[:] = np.arange(10.0)
    s = "abcd"
    v_name[:] = netCDF4.stringtochar(np.array([s], dtype="S128"))  # type: ignore
    v_scalar[:] = -1.0
    return ncfile


def test_ncopen():
    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        ncfile = tmp.joinpath("test.nc")
        _make_dataset(ncfile)
        with ncopen(ncfile) as d:
            assert d.filepath() == ncfile.as_posix()
            assert list(d.variables.keys()) == ["time", "value", "name", "scalar"]
            assert d.variables["time"][0] == 0
            # d is open, and ncopen(d) will return itself
            with ncopen(d) as dd:
                assert dd is d
                assert dd.variables["time"][1] == 1
            # d and dd are still open after the inner context
            assert d.isopen()
            assert dd.isopen()

        # d should be closed after the outer context
        assert not d.isopen()

        with pytest.raises(RuntimeError, match="NetCDF: Not a valid ID"):
            assert d.variables["time"][0] == 0

        with pytest.raises(RuntimeError, match="dataset is closed"):
            ncopen(d)


def test_ncstr():
    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        ncfile = tmp.joinpath("test.nc")
        _make_dataset(ncfile)

        with ncopen(ncfile) as d:
            s = ncstr(d.variables["name"])
            assert s == "abcd"

            with pytest.raises(RuntimeError, match="var is not a string"):
                ncstr(d.variables["time"])


def test_ncinfo():
    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        ncfile = tmp.joinpath("test.nc")
        _make_dataset(ncfile)
        with ncopen(ncfile) as d:
            s = ncinfo(d)
            logger.debug(f"ncinfo:\n{s}")
            assert "time_len(3), value_len(10), name_len(128)" in ncinfo(d)


def test_nc_node_mapper():
    node_map = {
        "v_t": "time",
        "v_v": "value",
        "v_n": "name",
        "v_s": "scalar",
        "d_t": "time_len",
        "d_n": "name_len",
    }

    nm = NcNodeMapper(nc_node_map=node_map)

    # check map
    assert nm.nc_node_map == node_map

    # getitem
    assert nm["v_t"] == node_map["v_t"]

    # getitem not exists
    assert nm["not_exist"] == "not_exist"

    # access ncnode is error:
    with pytest.raises(NcNodeMapperError, match="no netCDF dataset"):
        _ = nm.nc_node

    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        ncfile = tmp.joinpath("test.nc")
        _make_dataset(ncfile)

        with nm.open(ncfile):
            # check map
            assert isinstance(nm.nc_node, netCDF4.Dataset)  # type: ignore
            # check var
            assert nm.has_var("v_t")
            assert nm.has_dim("d_t")

            # get var
            assert nm.get_var("v_t")[2] == 2
            assert nm.get_var("v_n")[0] == b"a"

            # get dim
            assert nm.get_dim("d_t") == 3
            assert nm.get_dim("d_n") == 128

            # get scalar
            assert nm.get_scalar("v_s") == -1.0

            # get str
            assert nm.get_str("v_n") == "abcd"
            # get_* can also with with original varialbe name
            assert nm.get_str("name") == "abcd"

            # get_value
            assert nm.get_value("v_v") == nm.get_value("value")
            assert nm.get_value("v_n") == "abcd"
            assert nm.get_value("d_t") == 3

        # nm is closed
        with pytest.raises(NcNodeMapperError, match="no netCDF dataset"):
            _ = nm.get_value("v_s")

        # nm can be reopen
        # open file
        with nm.open(ncfile):
            # get_value
            assert nm.get_value("v_v") == nm.get_value("value")
            assert nm.get_value("v_n") == "abcd"
            assert nm.get_value("d_t") == 3


def test_nc_node_mapper_tree():
    node_map = {
        "v": {
            "v_t": "time",
            "v_v": "value",
            "v_n": "name",
            "v_s": "scalar",
        },
        "d": {
            "d_t": "time_len",
            "d_n": "name_len",
        },
    }

    nm = NcNodeMapperTree(nc_node_map=node_map)

    # check map
    assert nm["v"].nc_node_map == node_map["v"]
    assert nm["d"].nc_node_map == node_map["d"]

    # access ncnode is error:
    with pytest.raises(NcNodeMapperError, match="no netCDF dataset"):
        _ = nm.nc_node

    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        ncfile = tmp.joinpath("test.nc")
        _make_dataset(ncfile)

        with nm.open(ncfile):
            # check map
            assert isinstance(nm.nc_node, netCDF4.Dataset)  # type: ignore
            assert nm["v"].nc_node is nm.nc_node
            assert nm["d"].nc_node is nm.nc_node
            # check var
            assert nm["v"].has_var("v_t")
            assert nm["d"].has_dim("d_t")

            # get var
            assert nm["v"].get_var("v_t")[2] == 2
            assert nm["v"].get_var("v_n")[0] == b"a"

            # get dim
            assert nm["d"].get_dim("d_t") == 3
            assert nm["d"].get_dim("d_n") == 128

            # get scalar
            assert nm["v"].get_scalar("v_s") == -1.0

            # get str
            assert nm["v"].get_str("v_n") == "abcd"
            # get_* can also with with original varialbe name
            assert nm["v"].get_str("name") == "abcd"

            # get_value
            assert nm["v"].get_value("v_v") == nm["v"].get_value("value")
            assert nm["v"].get_value("v_n") == "abcd"
            assert nm["d"].get_value("d_t") == 3

        # nm is closed
        with pytest.raises(NcNodeMapperError, match="no netCDF dataset"):
            _ = nm["v"].get_value("v_s")

        # nm can be reopen
        # open file
        with nm.open(ncfile):
            # get_value
            assert nm["v"].get_value("v_v") == nm["v"].get_value("value")
            assert nm["v"].get_value("v_n") == "abcd"
            assert nm["d"].get_value("d_t") == 3
