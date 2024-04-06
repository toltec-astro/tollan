import pytest

from tollan.utils.general import (
    dict_from_flat_dict,
    dict_from_regex_match,
    dict_to_flat_dict,
    rupdate,
)


def test_dict_from_flat_dict():
    fd = {"a.0.b": True, "a.1": 1, "b": "value", "a.+0": {"p": "q"}}
    d = dict_from_flat_dict(fd)
    assert d == {"a": {"0": {"b": True}, "1": 1, "+0": {"p": "q"}}, "b": "value"}


def test_dict_to_flat_dict():
    d = {"a": {"0": {"b": True}, "1": 1, "+0": {"p": "q"}}, "b": "value"}
    fd = dict_to_flat_dict(d)
    assert fd == {"a.0.b": True, "a.1": 1, "b": "value", "a.+0.p": "q"}


def test_rupdate():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "+0": {"p": "q"}}, "b": "value"}
    rupdate(d, d1)
    assert d == {"a": [{"p": "q"}, {"b": True}, 1], "b": "value"}


def test_rupdate_extend():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "+": {"p": "q"}}, "b": "value"}
    rupdate(d, d1)
    assert d == {"a": [{"b": True}, 1, {"p": "q"}], "b": "value"}


def test_rupdate_replace():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "+:": ["p", "q"]}, "b": "value"}
    rupdate(d, d1)
    assert d == {"a": ["p", "q"], "b": "value"}


def test_rupdate2():
    d = {}
    u0 = {"a": {"b": {"c": 1}}}
    rupdate(d, u0)
    assert d == u0
    rupdate(d, {"a": {"c": "d"}})
    assert d == {"a": {"b": {"c": 1}, "c": "d"}}
    assert u0 == {"a": {"b": {"c": 1}}}
    rupdate(u0, {"a": {"b": {"c": "some_value"}}})
    assert d == {"a": {"b": {"c": 1}, "c": "d"}}
    assert u0 == {"a": {"b": {"c": "some_value"}}}


def test_rupdate_not_copy_subdict():
    d = {}
    u0 = {"a": {"b": {"c": 1}}}
    rupdate(d, u0, copy_subdict=False)
    assert d == u0
    rupdate(d, {"a": {"c": "d"}})
    assert d == {"a": {"b": {"c": 1}, "c": "d"}}
    # u also get updated because the subdict is not copied
    assert u0 == {"a": {"b": {"c": 1}, "c": "d"}}


def test_rupdate_list():
    d = []
    u0 = {0: 1}
    with pytest.raises(IndexError, match="list index out of range"):
        rupdate(d, u0)
    d = [2, 3]
    u0 = {0: {"a": 1}}
    rupdate(d, u0, copy_subdict=False)
    assert d == [{"a": 1}, 3]
    rupdate(d, {0: {"b": 2}})
    assert d == [{"a": 1, "b": 2}, 3]
    assert u0 == {0: {"a": 1, "b": 2}}


def test_rupdate_append_list():
    d = []
    u0 = {"+": {"a": 1}, "+1": {"b": 2}}
    rupdate(d, u0, copy_subdict=False)
    assert d == [{"a": 1}, {"b": 2}]
    rupdate(d, {1: {"c": 1}})
    assert d == [{"a": 1}, {"b": 2, "c": 1}]
    assert d == [{"a": 1}, {"b": 2, "c": 1}]
    assert u0["+1"] == {"b": 2, "c": 1}


def test_rupdate_list_nested():
    d = {"m": [], "n": [{"d": 1}]}
    u0 = {"m": {"+": {"a": 1}, "+1": {"b": 2}}, "n": {0: {"d": 2}}}
    rupdate(d, u0, copy_subdict=False)
    assert d == {"m": [{"a": 1}, {"b": 2}], "n": [{"d": 2}]}


def test_dict_from_regex_match():
    pattern = r"(?P<key1>\d+)_(?P<key2>\w+)?"
    assert dict_from_regex_match(pattern, "01_abc") == {"key1": "01", "key2": "abc"}

    assert dict_from_regex_match(
        pattern,
        "01_abc",
        type_dispatcher={
            "key1": int,
            "key2": str.upper,
        },
    ) == {"key1": 1, "key2": "ABC"}
