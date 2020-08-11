#! /usr/bin/env python

from ..misc import dict_from_regex_match


def test_dict_from_regex_match():
    pattern = r'(?P<key1>\d+)_(?P<key2>\w+)?'
    assert dict_from_regex_match(pattern, '01_abc') == {
            'key1': '01',
            'key2': 'abc'
            }

    assert dict_from_regex_match(pattern, '01_abc', type_dispatcher={
        'key1': int,
        'key2': str.upper,
        }) == {
            'key1': 1,
            'key2': 'ABC'
            }
