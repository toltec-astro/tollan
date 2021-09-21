#!/usr/bin/env python

from ..misc import rupdate


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
