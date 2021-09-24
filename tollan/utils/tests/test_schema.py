#! /usr/bin/env python

from ..schema import make_nested_optional_defaults
from schema import Schema, Optional


def test_make_nested_optional_defaults():
    s_in = Schema({
            Optional('test_default_dict'): {
                Optional('key1', default='value1'): str,
                Optional('key2', default=10): int,
                Optional('key3'): {
                    Optional('nested1', default=1): int,
                    Optional('nested2', default=42): int
                    }
                }
            })

    s_out = make_nested_optional_defaults(s_in, return_schema=True)

    # s_int does not have nested defaults attached
    assert s_in.validate(dict()) == dict()
    assert s_out.validate(dict()) == {
            'test_default_dict':  {
                'key1': 'value1',
                'key2': 10,
                'key3': {
                    'nested1': 1,
                    'nested2': 42,
                    }
                }
            }
