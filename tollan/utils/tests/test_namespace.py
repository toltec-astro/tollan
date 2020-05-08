#! /usr/bin/env python

from .. import namespace as ns
from copy import deepcopy
import pytest


class MyNamespace(ns.Namespace):
    pass


def test_prepare_dict():
    d = {
            'a': 0,
            'b': {}
            }
    assert ns._prepare_dict(
            d,
            b={'c': 1}
            ) == {
                'a': 0,
                'b': {'c': 1}
                }
    assert d['b'] == {'c': 1}


def test_prepare_dict_deepcopy():
    d = {
            'a': 0,
            'b': {}
            }
    assert ns._prepare_dict(
            d,
            b={'c': 1},
            _namespace_from_dict_op=deepcopy
            ) == {
                'a': 0,
                'b': {'c': 1}
                }
    assert d['b'] == {}


def test_prepare_dict_op_override():

    def identity(x):
        return x

    d = {
            'a': 0,
            'b': {},
            '_namespace_from_dict_op': identity
            }
    assert ns._prepare_dict(
            d,
            b={'c': 1},
            _namespace_from_dict_op=deepcopy
            ) == {
                'a': 0,
                'b': {'c': 1},
                '_namespace_from_dict_op': identity
                }
    assert d['b'] == {'c': 1}


def test_get_namespace_type():
    d = {
            'a': 0,
            'b': {},
            'type': MyNamespace,
            'type2': 'tollan.utils.namespace:NamespaceMixin',
            '__class__': 'non_existing_namespace',
            '__class__2': str
            }
    assert ns._get_namespace_type(
            d,
            _namespace_type_key='type',
            _namespace_default_type=None
            ) == MyNamespace
    assert ns._get_namespace_type(
            d,
            _namespace_type_key='type2',
            _namespace_default_type=None
            ) == ns.NamespaceMixin
    assert ns._get_namespace_type(
            d,
            _namespace_type_key='type2',
            _namespace_default_type=MyNamespace
            ) == ns.NamespaceMixin
    assert ns._get_namespace_type(
            d,
            _namespace_type_key='non_exist',
            _namespace_default_type=MyNamespace
            ) == MyNamespace
    with pytest.raises(
            ns.NamespaceNotFoundError, match=r".* missing type_key .*"):
        ns._get_namespace_type(
            d,
            _namespace_type_key='non_exist',
            _namespace_default_type=None
            )
    with pytest.raises(
            ns.NamespaceNotFoundError, match=r".* import namespace type .*"):
        ns._get_namespace_type(
            d,
            _namespace_type_key='__class__',
            _namespace_default_type=None
            )
    with pytest.raises(
            ns.NamespaceNotFoundError,
            match=r".* class of NamespaceMixin expected, got .*"):
        ns._get_namespace_type(
            d,
            _namespace_type_key='__class__2',
            _namespace_default_type=MyNamespace
            )


def test_object_from_dict():
    d = {
            'a': 0,
            'b': {'c': 1},
            'type': MyNamespace,
            'type2': 'tollan.utils.namespace:NamespaceMixin',
            }
    o = ns.object_from_dict(
            d,
            _namespace_from_dict_op=lambda x: x,
            _namespace_type_key='type',
            b={'c': (1, 2)}
            )
    assert o.a == 0 and o.b == {'c': (1, 2)} and d['b'] == {'c': (1, 2)}


def test_dict_from_object():
    d = {
            'a': 0,
            'b': {'c': 1},
            'type': MyNamespace,
            'type2': 'tollan.utils.namespace:NamespaceMixin',
            }
    o = MyNamespace(a=0, b={'c': 1})
    d = o.to_dict(to_dict_op=lambda x: x.__dict__)
    assert o.a == d['a'] and o.b == {'c': 1}
    d['b']['c'] = (1, 2)
    assert o.b == {'c': (1, 2)}


def test_dict_namespace_roundtrip():
    o = MyNamespace(a=0, b={'c': 1})
    print(o.to_dict())
    o1 = ns.object_from_dict(o.to_dict())
    assert o1.a == o.a and o1.b == o.b
    with pytest.raises(
            ns.NamespaceTypeError,
            match=r"invalid namespace type .+"):
        ns.NamespaceMixin.from_dict(o.to_dict())
