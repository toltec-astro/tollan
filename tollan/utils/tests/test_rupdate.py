#!/usr/bin/env python

from ..misc import rupdate
import pytest


def test_rupdate():

    d = dict()
    u0 = {'a': {'b': {'c': 1}}}
    rupdate(d, u0)
    assert d == u0
    rupdate(d, {'a': {'c': 'd'}})
    assert d == {
        'a': {'b': {'c': 1}, 'c': 'd'}
        }
    assert u0 == {'a': {'b': {'c': 1}}}
    rupdate(u0, {'a': {'b': {'c': 'some_value'}}})
    assert d == {
        'a': {'b': {'c': 1}, 'c': 'd'}
        }
    assert u0 == {'a': {'b': {'c': 'some_value'}}}


def test_rupdate_not_copy_subdict():

    d = dict()
    u0 = {'a': {'b': {'c': 1}}}
    rupdate(d, u0, copy_subdict=False)
    assert d == u0
    rupdate(d, {'a': {'c': 'd'}})
    assert d == {
        'a': {'b': {'c': 1}, 'c': 'd'}
        }
    # u also get updated because the subdict is not copied
    assert u0 == {'a': {'b': {'c': 1}, 'c': 'd'}}


def test_rupdate_list():

    d = []
    u0 = {0: 1}
    with pytest.raises(IndexError, match='list assignment index out of range'):
        rupdate(d, u0)
    d = [2, 3]
    u0 = {0: {'a': 1}}
    rupdate(d, u0, copy_subdict=False)
    assert (d == [{'a': 1}, 3])
    rupdate(d, {0: {'b': 2}})
    assert (d == [{'a': 1, 'b': 2}, 3])
    assert (u0 == {0: {'a': 1, 'b': 2}})


def test_rupdate_append_list():

    d = []
    u0 = {'<<': {'a': 1}, "<<1": {'b': 2}}
    rupdate(d, u0, copy_subdict=False)
    assert d == [{'a': 1}, {'b': 2}]
    rupdate(d, {1: {'c': 1}})
    assert d == [{'a': 1}, {'b': 2, 'c': 1}]
    assert d == [{'a': 1}, {'b': 2, 'c': 1}]
    assert u0['<<1'] == {'b': 2, 'c': 1}


def test_rupdate_list_nested():

    d = {'m': [], 'n': [{'d': 1}]}
    u0 = {'m': {'<<': {'a': 1}, "<<1": {'b': 2}}, 'n': {0: {'d': 2}}}
    rupdate(d, u0, copy_subdict=False)
    assert d == {'m': [{'a': 1}, {'b': 2}], 'n': [{'d': 2}]}
