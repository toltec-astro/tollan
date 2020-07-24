#! /usr/bin/env python

from .. import get_pkg_data_path
from ..nc import ncopen, ncstr, ncinfo, NcNodeMapper, NcNodeMapperError
import pytest
import netCDF4


def test_ncopen():
    # local file
    filepath = get_pkg_data_path().joinpath('tests/test_nc.nc')

    with ncopen(filepath) as d:
        assert d.filepath() == filepath.as_posix()
        assert list(d.variables.keys()) == ['x', 's', 't']
        assert d.variables['x'][0, 0] == 0
        # d is open, and ncopen(d) will return itself
        with ncopen(d) as dd:
            assert dd is d
            dd.variables['x'][0, 1] == 1
        # d is still open after the context
        assert d.isopen()
        assert dd.isopen()

    # d should be closed
    assert not d.isopen()

    with pytest.raises(RuntimeError, match='NetCDF: Not a valid ID'):
        assert d.variables['x'][0] == 0

    with pytest.raises(RuntimeError, match='dataset is closed'):
        ncopen(d)


def test_ncstr():

    # local file
    filepath = get_pkg_data_path().joinpath('tests/test_nc.nc')

    with ncopen(filepath) as d:
        s = ncstr(d.variables['s'])
        assert s == 'abc'

        with pytest.raises(RuntimeError, match='var is not a string'):
            ncstr(d.variables['x'])


def test_ncinfo():

    filepath = get_pkg_data_path().joinpath('tests/test_nc.nc')

    with ncopen(filepath) as d:
        assert 'dims: [a: 5, b: 3]' in ncinfo(d)


def test_nc_node_mapper():

    filepath = get_pkg_data_path().joinpath('tests/test_nc.nc')

    map_ = {
        'v_x': 'x',
        'v_s': 's',
        'v_t': 't',
        'd_a': 'a',
        'd_b': 'b',
        }

    nm = NcNodeMapper(nc_node_map=map_)

    # check map
    assert nm.nc_node_map == map_

    # getitem
    assert nm['v_x'] == map_['v_x']

    # getitem not exists
    assert nm['not_exist'] == 'not_exist'

    # access ncnode is error:
    with pytest.raises(NcNodeMapperError, match='no netCDF dataset'):
        nm.nc_node

    # open file
    with nm.open(filepath):
        # check map
        assert isinstance(nm.nc_node, netCDF4.Dataset)
        # check var
        assert nm.hasvar('v_t')
        assert nm.hasdim('d_a')

        # get var
        assert nm.getvar('v_x')[0, 2] == 2
        assert nm.getvar('v_s')[0] == b'a'

        # get dim
        assert nm.getdim('d_a') == 5
        assert nm.getdim('d_b') == 3

        # get scalar
        assert nm.getscalar('v_t') == 3

        # getstr
        assert nm.getstr('v_s') == 'abc'
        # get* can also with with original varialbe name
        assert nm.getstr('s') == 'abc'

        # getany
        assert nm.getany('v_x') == nm.getvar('v_x')
        assert nm.getany('v_s') == 'abc'
        assert nm.getany('v_t') == 3

    # nm is closed
    with pytest.raises(NcNodeMapperError, match='no netCDF dataset'):
        nm.getany('v_s') == 'abc'

    # nm can be reopen
    # open file
    with nm.open(filepath):
        # getany
        assert nm.getany('v_x') == nm.getvar('v_x')
        assert nm.getany('v_s') == 'abc'
        assert nm.getany('v_t') == 3
