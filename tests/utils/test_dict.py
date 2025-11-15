"""Tests for tollan.utils.collections module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tollan.utils.dict import (
    add_to_dict,
    dict_from_flat_dict,
    dict_from_regex_match,
    dict_product,
    dict_to_flat_dict,
    rupdate,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_dict_from_flat_dict():
    fd = {"a.0.b": True, "a.1": 1, "b": "value"}
    d = dict_from_flat_dict(fd)
    assert d == {"a": {"0": {"b": True}, "1": 1}, "b": "value"}


def test_dict_to_flat_dict():
    d = {"a": {"0": {"b": True}, "1": 1}, "b": "value"}
    fd = dict_to_flat_dict(d)
    assert fd == {"a.0.b": True, "a.1": 1, "b": "value"}


def test_rupdate():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "[:0]": {"p": "q"}}, "b": "value"}
    rupdate(d, d1)
    assert d == {"a": [{"p": "q"}, {"b": True}, 1], "b": "value"}


def test_rupdate_extend():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "[]": {"p": "q"}}, "b": "value"}
    rupdate(d, d1)
    assert d == {"a": [{"b": True}, 1, {"p": "q"}], "b": "value"}


def test_rupdate_replace():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "[:]": ["p", "q"]}, "b": "value"}
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
    with pytest.raises(IndexError, match="List index .* out of range"):
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
    u0 = {"[]": {"a": 1}, "[:0]": {"b": 2}}
    rupdate(d, u0, copy_subdict=False)
    assert d == [{"b": 2}, {"a": 1}]
    rupdate(d, {1: {"c": 1}})
    assert d == [{"b": 2}, {"a": 1, "c": 1}]
    assert u0["[]"] == {"a": 1, "c": 1}


def test_rupdate_list_nested():
    d = {"m": [], "n": [{"d": 1}]}
    u0 = {"m": {"[]": {"a": 1}, "[:0]": {"b": 2}}, "n": {0: {"d": 2}}}
    rupdate(d, u0, copy_subdict=False)
    assert d == {"m": [{"b": 2}, {"a": 1}], "n": [{"d": 2}]}


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


def test_list_dsl_slice_syntax():
    """Test new slice-based DSL syntax."""
    from tollan.utils.dict import ListDSL, ListOperation

    # Test [:] - replace entire list
    dsl = ListDSL.parse("[:]")
    assert dsl is not None
    assert dsl.operation == ListOperation.SLICE
    assert dsl.slice_obj == slice(None, None, None)

    # Test [:0] - prepend
    dsl = ListDSL.parse("[:0]")
    assert dsl is not None
    assert dsl.operation == ListOperation.SLICE
    assert dsl.slice_obj == slice(None, 0, None)

    # Test [1:3] - replace slice
    dsl = ListDSL.parse("[1:3]")
    assert dsl is not None
    assert dsl.operation == ListOperation.SLICE
    assert dsl.slice_obj == slice(1, 3, None)

    # Test [] - extend at end (special case)
    dsl = ListDSL.parse("[]")
    assert dsl is not None
    assert dsl.operation == ListOperation.SLICE
    assert dsl.slice_obj is None
    assert dsl.to_slice(5) == slice(5, 5)

    # Test [2:2] - insert at position
    dsl = ListDSL.parse("[2:2]")
    assert dsl is not None
    assert dsl.operation == ListOperation.SLICE
    assert dsl.slice_obj == slice(2, 2, None)

    # Test negative indices
    dsl = ListDSL.parse("[-1:]")
    assert dsl is not None
    assert dsl.slice_obj == slice(-1, None, None)

    # Test with step
    dsl = ListDSL.parse("[::2]")
    assert dsl is not None
    assert dsl.slice_obj == slice(None, None, 2)

    # Test plain integer indices (now handled by DSL)
    dsl = ListDSL.parse("0")
    assert dsl is not None
    assert dsl.operation == ListOperation.UPDATE
    assert dsl.index == 0

    dsl = ListDSL.parse("-1")
    assert dsl is not None
    assert dsl.operation == ListOperation.UPDATE
    assert dsl.index == -1

    # Test bracket-wrapped integers
    dsl = ListDSL.parse("[0]")
    assert dsl is not None
    assert dsl.operation == ListOperation.UPDATE
    assert dsl.index == 0

    # Test non-DSL (should return None)
    assert ListDSL.parse("abc") is None
    assert ListDSL.parse("+") is None


def test_rupdate_slice_prepend():
    """Test [:0] prepends to list."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {"[:0]": [0]}})
    assert d["items"] == [0, 1, 2, 3]


def test_rupdate_slice_extend():
    """Test [] extends list at end."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {"[]": [4, 5]}})
    assert d["items"] == [1, 2, 3, 4, 5]


def test_rupdate_slice_replace():
    """Test [N:M] replaces slice."""
    d = {"items": [1, 2, 3, 4, 5]}
    rupdate(d, {"items": {"[1:3]": [10, 20]}})
    assert d["items"] == [1, 10, 20, 4, 5]


def test_rupdate_slice_delete():
    """Test [N:M] with empty list deletes elements."""
    d = {"items": [1, 2, 3, 4, 5]}
    rupdate(d, {"items": {"[1:3]": []}})
    assert d["items"] == [1, 4, 5]


def test_rupdate_slice_insert():
    """Test [N:N] inserts at position."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {"[1:1]": [10]}})
    assert d["items"] == [1, 10, 2, 3]


def test_rupdate_slice_replace_all():
    """Test [:] replaces entire list."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {"[:]": [10, 20]}})
    assert d["items"] == [10, 20]


def test_rupdate_integer_index():
    """Test integer keys still update at index."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {0: 10, 2: 30}})
    assert d["items"] == [10, 2, 30]


def test_rupdate_negative_index():
    """Test negative integer indices work."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {-1: 99}})
    assert d["items"] == [1, 2, 99]


def test_rupdate_slice_with_step():
    """Test slice with step parameter."""
    d = {"items": [0, 1, 2, 3, 4, 5]}
    # Replace every other element
    rupdate(d, {"items": {"[::2]": [10, 20, 30]}})
    assert d["items"] == [10, 1, 20, 3, 30, 5]


def test_rupdate_mixed_operations():
    """Test combining index updates and slice operations."""
    d = {"items": [1, 2, 3]}
    rupdate(d, {"items": {0: 10, "[]": [4, 5], 1: 20}})
    assert d["items"] == [10, 20, 3, 4, 5]


def test_rupdate_chained_extend_then_update():
    """Test chained operations: extend then update last element."""
    d = {"items": [1, 2, 3]}
    # First extend with [4, 5], then update last element to 10
    rupdate(d, {"items": {"[]": [4, 5], -1: 10}})
    assert d["items"] == [1, 2, 3, 4, 10]


def test_rupdate_chained_update_then_extend():
    """Test chained operations: update then extend - order matters!"""
    d = {"items": [1, 2, 3]}
    # First update last element to 10, then extend with [4, 5]
    rupdate(d, {"items": {-1: 10, "[]": [4, 5]}})
    assert d["items"] == [1, 2, 10, 4, 5]


def test_rupdate_order_dependency():
    """Test that operation order is preserved (Python 3.7+ dict ordering)."""
    # Order 1: prepend, update index 1, extend
    d1 = {"items": [1, 2, 3]}
    rupdate(d1, {"items": {"[:0]": [0], 1: 100, "[]": [4, 5]}})
    assert d1["items"] == [0, 100, 2, 3, 4, 5]

    # Order 2: update index 1, prepend, extend
    d2 = {"items": [1, 2, 3]}
    rupdate(d2, {"items": {1: 100, "[:0]": [0], "[]": [4, 5]}})
    assert d2["items"] == [0, 1, 100, 3, 4, 5]


def test_dict_product():
    """Test Cartesian product of dictionaries."""
    result = list(dict_product(a=[1, 2], b=["x", "y"]))
    expected = [
        {"a": 1, "b": "x"},
        {"a": 1, "b": "y"},
        {"a": 2, "b": "x"},
        {"a": 2, "b": "y"},
    ]
    assert result == expected


def test_dict_product_single_key():
    """Test dict_product with single key."""
    result = list(dict_product(a=[1, 2, 3]))
    expected = [{"a": 1}, {"a": 2}, {"a": 3}]
    assert result == expected


def test_dict_product_empty():
    """Test dict_product with empty inputs."""
    result = list(dict_product())
    assert result == [{}]


def test_add_to_dict():
    """Test add_to_dict decorator."""
    registry = {}

    @add_to_dict(registry, "my_func")
    def my_function():
        return "hello"

    assert "my_func" in registry
    assert registry["my_func"]() == "hello"


def test_add_to_dict_callable_key():
    """Test add_to_dict with callable key."""
    registry = {}

    @add_to_dict(registry, lambda f: f.__name__.upper())
    def my_function():
        return "hello"

    assert "MY_FUNCTION" in registry
    assert registry["MY_FUNCTION"]() == "hello"


def test_add_to_dict_exist_ok_false():
    """Test add_to_dict with exist_ok=False raises on duplicate."""
    registry = {"existing": "value"}

    with pytest.raises(ValueError, match="key=existing exist"):

        @add_to_dict(registry, "existing", exist_ok=False)
        def my_function():
            return "hello"


def test_add_to_dict_exist_ok_true():
    """Test add_to_dict with exist_ok=True allows overwrite."""

    registry: dict[str, Callable[[], str]] = {}
    registry["existing"] = lambda: "old_value"

    @add_to_dict(registry, "existing", exist_ok=True)
    def my_function():
        return "new_value"

    assert registry["existing"]() == "new_value"
