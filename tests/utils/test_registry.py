"""Unique keyed registration and mapping access."""

from collections.abc import Mapping, MutableMapping
from operator import delitem, setitem
from typing import assert_type

import pytest

from tollan.utils.registry import Registry, RegistryView


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


@pytest.mark.parametrize("read_only_view", [False, True])
def test_mutable_mapping_operations_are_not_available(read_only_view):
    registry = Registry[str, int]()
    registry.register("entry", 1)
    lookup = registry.view if read_only_view else registry
    assert not isinstance(lookup, MutableMapping)
    with pytest.raises(TypeError):
        setitem(lookup, "entry", 2)  # ty: ignore[no-matching-overload] -- exercise invalid mutation.
    with pytest.raises(TypeError):
        delitem(lookup, "entry")  # ty: ignore[no-matching-overload] -- exercise invalid mutation.
    assert not hasattr(lookup, "update")
    assert dict(registry) == {"entry": 1}


def test_read_only_view_tracks_registrations_without_copying_values():
    registry = Registry[str, list[int]]()
    view = registry.view
    assert_type(view, RegistryView[str, list[int]])
    assert not view
    assert not hasattr(view, "register")
    keys = view.keys()
    values = view.values()
    value = [1]
    registry.register("first", value)
    registry.register("second", [2])
    assert len(view) == 2
    assert list(keys) == ["first", "second"]
    assert list(values) == [[1], [2]]
    assert list(view.items()) == list(registry.items())
    assert_type(view["first"], list[int])
    assert view["first"] is value
    value.append(3)
    assert view["first"] == [1, 3]
    assert view.get("absent") is None
    with pytest.raises(KeyError, match="absent"):
        view["absent"]


def test_view_subclass_adds_typed_lookup_properties():
    class NamedEntries(RegistryView[str, int]):
        @property
        def first(self) -> int:
            return self["first"]

    registry = Registry[str, int]()
    view = NamedEntries(registry.view)
    registry.register("first", 1)
    assert_type(view.first, int)
    assert view.first == view["first"] == 1
    registry.register("extension", 2)
    assert list(view) == ["first", "extension"]
    assert not hasattr(view, "register")
