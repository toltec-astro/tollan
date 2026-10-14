"""Tests for tollan.utils.collections module."""

from __future__ import annotations

from collections import UserDict
from copy import copy
from typing import Any

import pytest

from tollan.utils.dict import (
    ListOperation,
    dict_from_flat_dict,
    dict_from_regex_match,
    dict_product,
    dict_to_flat_dict,
    rupdate,
)


def test_list_operation_string_values():
    assert {
        name: operation.value for name, operation in ListOperation.__members__.items()
    } == {
        "update": "update",
        "slice": "slice",
    }
    for operation in ListOperation:
        assert operation == operation.value
        assert str(operation) == operation.value
        assert ListOperation(operation.value) is operation


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


def test_rupdate_not_copy_subcontainers():
    d = {}
    u0 = {"a": {"b": {"c": 1}}}
    rupdate(d, u0, copy_subcontainers=False)
    assert d == u0
    rupdate(d, {"a": {"c": "d"}}, copy_subcontainers=False)
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
    rupdate(d, u0, copy_subcontainers=False)
    assert d == [{"a": 1}, 3]
    rupdate(d, {0: {"b": 2}}, copy_subcontainers=False)
    assert d == [{"a": 1, "b": 2}, 3]
    assert u0 == {0: {"a": 1, "b": 2}}


def test_rupdate_append_list():
    d = []
    u0 = {"[]": {"a": 1}, "[:0]": {"b": 2}}
    rupdate(d, u0, copy_subcontainers=False)
    assert d == [{"b": 2}, {"a": 1}]
    rupdate(d, {1: {"c": 1}}, copy_subcontainers=False)
    assert d == [{"b": 2}, {"a": 1, "c": 1}]
    assert u0["[]"] == {"a": 1, "c": 1}


def test_rupdate_list_nested():
    d = {"m": [], "n": [{"d": 1}]}
    u0 = {"m": {"[]": {"a": 1}, "[:0]": {"b": 2}}, "n": {0: {"d": 2}}}
    rupdate(d, u0, copy_subcontainers=False)
    assert d == {"m": [{"b": 2}, {"a": 1}], "n": [{"d": 2}]}


def test_rupdate_shallow_copies_assigned_lists_by_default():
    source = {"section": {"values": [1, {"nested": [2]}]}}
    merged = {}
    rupdate(merged, source)
    assert merged["section"] is not source["section"]
    assert merged["section"]["values"] is not source["section"]["values"]
    assert merged["section"]["values"][1] is source["section"]["values"][1]
    rupdate(merged, {"section": {"values": {0: 9, "[]": [3]}}})
    assert merged == {"section": {"values": [9, {"nested": [2]}, 3]}}
    assert source == {"section": {"values": [1, {"nested": [2]}]}}


def test_rupdate_detaches_nested_objects_when_updated():
    source = {"items": [{"value": 1}]}
    merged, sibling = {}, {}
    rupdate(merged, source)
    rupdate(sibling, source)
    assert merged["items"][0] is source["items"][0]
    rupdate(merged, {"items": {0: {"value": 2}}})
    assert merged["items"] is not source["items"]
    assert merged["items"][0] is not source["items"][0]
    assert merged == {"items": [{"value": 2}]}
    assert source == sibling == {"items": [{"value": 1}]}
    rupdate(source, {"items": {0: {"value": 3}}})
    assert source == {"items": [{"value": 3}]}
    assert merged == {"items": [{"value": 2}]}
    assert sibling == {"items": [{"value": 1}]}


@pytest.mark.parametrize("copy_subcontainers", [True, False])
@pytest.mark.parametrize("container", ["dict", "list"])
@pytest.mark.parametrize("destination", ["scalar", "list_index"])
def test_rupdate_inserted_container_ownership(
    copy_subcontainers, container, destination
):
    leaf = {"items": [1]}
    incoming = {"child": leaf} if container == "dict" else [leaf]
    target: dict[int, Any] | list[Any] = (
        [None] if destination == "list_index" else {0: None}
    )

    rupdate(target, {0: incoming}, copy_subcontainers=copy_subcontainers)
    inserted = target[0]
    assert inserted is not None
    assert (inserted is incoming) is not copy_subcontainers
    inserted_leaf = inserted["child"] if container == "dict" else inserted[0]
    assert inserted_leaf is leaf
    inserted_leaf["items"].append(2)
    assert leaf["items"] == [1, 2]


@pytest.mark.parametrize("copy_subcontainers", [True, False])
@pytest.mark.parametrize("key", ["[]", "[:0]", "[1:1]", "[0:1]", "[:]", "[::2]"])
@pytest.mark.parametrize("as_list", [True, False])
def test_rupdate_slice_container_ownership(copy_subcontainers, key, as_list):
    item = {"nested": [1]}
    target = [None, None]
    rupdate(
        target,
        {key: [item] if as_list else item},
        copy_subcontainers=copy_subcontainers,
    )
    inserted = next(value for value in target if value is not None)
    assert (inserted is item) is not copy_subcontainers
    inserted["new"] = 2
    assert ("new" in item) is not copy_subcontainers
    assert inserted["nested"] is item["nested"]
    inserted["nested"].append(2)
    assert item["nested"] == [1, 2]


def test_rupdate_append_then_patch_copies_only_the_inserted_dict():
    item = {"value": 1, "nested": []}
    updates = {"[]": [item], 0: {"value": 2}}
    target = []
    rupdate(target, updates)
    assert target == [{"value": 2, "nested": []}]
    assert item == {"value": 1, "nested": []}
    assert target[0]["nested"] is item["nested"]


def test_rupdate_repeated_insertions_get_independent_copies():
    item = {"value": 1}
    target = []
    rupdate(target, {"[]": [item, item], 0: {"value": 2}})
    assert target == [{"value": 2}, {"value": 1}]
    assert target[0] is not target[1]
    assert item == {"value": 1}


@pytest.mark.parametrize("copy_subcontainers", [True, False])
@pytest.mark.parametrize(
    ("key", "index"), [("[]", 1), ("[:0]", 0), ("[:]", 0), ("[::2]", 0)]
)
def test_rupdate_slice_then_nested_patches(copy_subcontainers, key, index):
    untouched = {"keep": []}
    item = {"values": [1], "untouched": untouched}
    target = [None]
    rupdate(
        target,
        {
            key: [item],
            index: {"values": {"[]": [2]}},
            f"[{index}]": {"values": {0: 9}},
        },
        copy_subcontainers=copy_subcontainers,
    )
    inserted = target[index]
    assert inserted is not None
    assert inserted["values"] == [9, 2]
    assert (inserted is item) is not copy_subcontainers
    assert (inserted["values"] is item["values"]) is not copy_subcontainers
    assert inserted["untouched"] is untouched
    assert item["values"] == ([1] if copy_subcontainers else [9, 2])


@pytest.mark.parametrize("prepare", [True, False])
def test_list_dsl_prepares_inserted_items(prepare):
    from tollan.utils.dict import ListDSL

    nested = {"value": 1}
    item = [nested]
    target = []
    dsl = ListDSL.parse("[]")
    assert dsl is not None
    assert dsl.apply(target, [item], prepare_value=copy if prepare else None)
    assert (target[0] is item) is not prepare
    assert target[0][0] is nested


@pytest.mark.parametrize("copy_subcontainers", [True, False])
@pytest.mark.parametrize("container", ["dict", "list"])
def test_rupdate_assignment_then_patch_reuses_owned_containers(
    copy_subcontainers, container
):
    child = {"value": 1}
    item = {0: child} if container == "dict" else [child]
    target = [None]
    rupdate(
        target,
        {0: item, "[0]": {0: {"value": 2}}},
        copy_subcontainers=copy_subcontainers,
    )
    inserted = target[0]
    assert inserted is not None
    assert inserted[0] == {"value": 2}
    assert child == {"value": 1 if copy_subcontainers else 2}


def test_rupdate_preserves_iterative_mapping_copy():
    source = UserDict({"a": UserDict({"b": 1})})
    target = {}
    rupdate(target, {"source": source})
    assert target == {"source": {"a": {"b": 1}}}
    assert target["source"] is not source
    assert target["source"]["a"] is not source["a"]


@pytest.mark.parametrize("copy_subcontainers", [True, False])
def test_rupdate_missing_key_is_distinct_from_existing_none(copy_subcontainers):
    incoming = {"nested": {"value": 1}}
    target = {"present": None}
    rupdate(
        target,
        {"missing": incoming, "present": incoming},
        copy_subcontainers=copy_subcontainers,
    )
    assert target == {"missing": incoming, "present": incoming}
    present, missing = target["present"], target["missing"]
    assert present is not None
    assert missing is not None
    assert (present is incoming) is not copy_subcontainers
    assert (missing is incoming) is not copy_subcontainers
    assert present["nested"] is incoming["nested"]
    assert (missing["nested"] is incoming["nested"]) is not copy_subcontainers


@pytest.mark.parametrize("copy_subcontainers", [True, False])
@pytest.mark.parametrize("value", [{"value": 1}, [1]])
def test_rupdate_empty_mapping_preserves_existing_container(copy_subcontainers, value):
    target = {"section": value}
    rupdate(target, {"section": {}}, copy_subcontainers=copy_subcontainers)
    assert target["section"] is value


@pytest.mark.parametrize("copy_subcontainers", [True, False])
def test_rupdate_empty_mapping_still_creates_or_replaces(copy_subcontainers):
    incoming = {}
    target = {"present": None}
    rupdate(
        target,
        {"missing": incoming, "present": incoming},
        copy_subcontainers=copy_subcontainers,
    )
    assert target == {"missing": {}, "present": {}}
    assert (target["missing"] is incoming) is not copy_subcontainers
    assert (target["present"] is incoming) is not copy_subcontainers


def test_rupdate_nested_empty_patch_copies_only_the_ancestor():
    child = {"value": 1}
    section = {"child": child}
    target = {"section": section}
    rupdate(target, {"section": {"child": {}}})
    assert target["section"] is not section
    assert target["section"]["child"] is child


def test_rupdate_deep_dict_merge_does_not_use_python_recursion():
    source = {}
    node = source
    for _ in range(1200):
        node["next"] = {}
        node = node["next"]
    target = {}
    rupdate(target, source)
    original, copied = source, target
    for _ in range(1200):
        assert copied is not original
        original, copied = original["next"], copied["next"]


def test_rupdate_preserves_non_container_objects():
    class Opaque:
        def __deepcopy__(self, memo):
            pytest.fail("rupdate must not deep-copy arbitrary objects")

    obj = Opaque()
    wrapped = ({"value": [1]},)
    source = {"items": [{"object": obj, "tuple": wrapped}], "keyed": {obj: obj}}
    target = {}
    rupdate(target, source)
    assert target["items"][0]["object"] is obj
    assert target["items"][0]["tuple"] is wrapped
    assert next(iter(target["keyed"])) is obj
    assert target["keyed"][obj] is obj


@pytest.mark.parametrize("copy_subcontainers", [True, False])
def test_rupdate_existing_destination_containers(copy_subcontainers):
    existing = {"values": [1]}
    target = {"section": existing}
    result = rupdate(
        target,
        {"section": {"values": {"[]": [2]}}},
        copy_subcontainers=copy_subcontainers,
    )
    assert result is None
    assert target == {"section": {"values": [1, 2]}}
    assert (target["section"] is existing) is not copy_subcontainers
    assert existing == {"values": [1] if copy_subcontainers else [1, 2]}


def test_rupdate_only_copies_traversed_paths():
    untouched = {"keep": []}
    item = UserDict({"values": [1], "untouched": untouched})
    original = {"items": [item]}
    target = {}
    rupdate(target, original)
    rupdate(target, {"items": {0: {"values": {"[]": [2]}}}})
    assert target == {"items": [{"values": [1, 2], "untouched": {"keep": []}}]}
    assert original["items"][0]["values"] == [1]
    assert isinstance(target["items"][0], UserDict)
    assert target["items"][0] is not item
    assert target["items"][0]["untouched"] is untouched


@pytest.mark.parametrize("copy_subcontainers", [True, False])
def test_rupdate_repeated_selectors_preserve_queued_updates(copy_subcontainers):
    original = {"a": 0, "nested": {"x": 0}}
    target = [original]
    rupdate(
        target,
        {0: {"a": 1, "nested": {"x": 1}}, "[0]": {"b": 2, "nested": {"y": 2}}},
        copy_subcontainers=copy_subcontainers,
    )
    assert target == [{"a": 1, "b": 2, "nested": {"x": 1, "y": 2}}]
    if copy_subcontainers:
        assert original == {"a": 0, "nested": {"x": 0}}
    else:
        assert target[0] is original


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
    assert dsl.operation == ListOperation.slice
    assert dsl.slice_obj == slice(None, None, None)

    # Test [:0] - prepend
    dsl = ListDSL.parse("[:0]")
    assert dsl is not None
    assert dsl.operation == ListOperation.slice
    assert dsl.slice_obj == slice(None, 0, None)

    # Test [1:3] - replace slice
    dsl = ListDSL.parse("[1:3]")
    assert dsl is not None
    assert dsl.operation == ListOperation.slice
    assert dsl.slice_obj == slice(1, 3, None)

    # Test [] - extend at end (special case)
    dsl = ListDSL.parse("[]")
    assert dsl is not None
    assert dsl.operation == ListOperation.slice
    assert dsl.slice_obj is None
    assert dsl.to_slice(5) == slice(5, 5)

    # Test [2:2] - insert at position
    dsl = ListDSL.parse("[2:2]")
    assert dsl is not None
    assert dsl.operation == ListOperation.slice
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
    assert dsl.operation == ListOperation.update
    assert dsl.index == 0

    dsl = ListDSL.parse("-1")
    assert dsl is not None
    assert dsl.operation == ListOperation.update
    assert dsl.index == -1

    # Test bracket-wrapped integers
    dsl = ListDSL.parse("[0]")
    assert dsl is not None
    assert dsl.operation == ListOperation.update
    assert dsl.index == 0

    # Test non-DSL (should return None)
    assert ListDSL.parse("abc") is None
    assert ListDSL.parse("+") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (":", slice(None)),
        ("::", slice(None)),
        (":0", slice(None, 0)),
        ("1:3", slice(1, 3)),
        ("-3:-1", slice(-3, -1)),
        ("::2", slice(None, None, 2)),
        ("::-1", slice(None, None, -1)),
        ("3:0:-2", slice(3, 0, -2)),
    ],
)
def test_list_dsl_slice_bounds(text, expected):
    from tollan.utils.dict import ListDSL

    assert ListDSL.parse(f"[{text}]") == ListDSL(
        ListOperation.slice, slice_obj=expected
    )


@pytest.mark.parametrize(
    ("key", "expected"),
    [("0", 0), ("-1", -1), ("[0]", 0), ("[-1]", -1), ("+1", 1)],
)
def test_list_dsl_integer_update_is_not_slice_assignment(key, expected):
    from tollan.utils.dict import ListDSL

    assert ListDSL.parse(key) == ListDSL(ListOperation.update, index=expected)


@pytest.mark.parametrize(
    "key", ["[+1]", "[+1:3]", "[1:3:+1]", "[ 1:3 ]", "[1:2:3:4]", "1:3"]
)
def test_list_dsl_preserves_unrecognized_syntax(key):
    from tollan.utils.dict import ListDSL

    assert ListDSL.parse(key) is None


def test_list_dsl_rejects_zero_step_before_assignment():
    from tollan.utils.dict import ListDSL

    with pytest.raises(ValueError, match="step cannot be zero"):
        ListDSL.parse("[::0]")
    values = [0, 1, 2]
    with pytest.raises(ValueError, match="step cannot be zero"):
        rupdate(values, {"[::0]": [3]})
    assert values == [0, 1, 2]


def test_rupdate_reverse_slice_assignment():
    values = [0, 1, 2]
    rupdate(values, {"[::-1]": [10, 20, 30]})
    assert values == [30, 20, 10]


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
