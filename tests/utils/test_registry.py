"""Unique keyed registration and mapping access."""

from collections.abc import Mapping, MutableMapping
from operator import delitem, setitem
from typing import assert_type

import pytest

from tollan.utils.registry import Registry


def test_mapping_lookup_and_registration_order():
    registry = Registry[str, int]()
    assert isinstance(registry, Mapping)
    assert not registry
    keys = registry.keys()
    registry.register("second", 2)
    registry.register("first", 1)
    assert_type(registry["first"], int)
    assert len(registry) == 2
    assert list(keys) == ["second", "first"]
    assert list(registry.values()) == [2, 1]
    assert list(registry.items()) == [("second", 2), ("first", 1)]
    assert dict(registry) == {"second": 2, "first": 1}
    assert registry.get("absent") is None
    with pytest.raises(KeyError, match="absent"):
        registry["absent"]


@pytest.mark.parametrize("same_object", [False, True])
def test_duplicate_key_preserves_existing_registration(same_object):
    registry = Registry[str, object]()
    original = object()
    registry.register("entry", original)
    candidate = original if same_object else object()
    with pytest.raises(ValueError, match="Key already registered: 'entry'"):
        registry.register("entry", candidate)
    assert list(registry) == ["entry"]
    assert registry["entry"] is original


@pytest.mark.parametrize("key", ["entry", 1, ("format", int), int])
def test_hashable_keys_and_independent_registries(key):
    registry = Registry()
    other = Registry()
    value = object()
    registry.register(key, value)
    assert registry[key] is value
    assert key not in other


def test_mutable_mapping_operations_are_not_available():
    registry = Registry[str, int]()
    registry.register("entry", 1)
    assert not isinstance(registry, MutableMapping)
    with pytest.raises(TypeError):
        setitem(registry, "entry", 2)  # ty: ignore[no-matching-overload] -- exercise invalid mutation.
    with pytest.raises(TypeError):
        delitem(registry, "entry")  # ty: ignore[no-matching-overload] -- exercise invalid mutation.
    assert not hasattr(registry, "update")
    assert dict(registry) == {"entry": 1}
