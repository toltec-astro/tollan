"""Dictionary and nested container utilities.

This module provides utilities for working with dictionaries and nested
container structures (dicts and lists), including recursive updates,
flattening/unflattening, and container manipulation.
"""

from __future__ import annotations

import collections.abc
import itertools
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping, MutableSequence

__all__ = [
    "add_to_dict",
    "dict_from_flat_dict",
    "dict_from_regex_match",
    "dict_product",
    "dict_to_flat_dict",
    "rupdate",
]


MT = collections.abc.MutableMapping
ST = collections.abc.MutableSequence


class ListOperation(Enum):
    """List update operations for rupdate DSL."""

    UPDATE = "update"  # Update existing item at index
    SLICE = "slice"  # Slice-based modification


@dataclass(frozen=True)
class ListDSL:
    """Parsed list DSL command.

    DSL Syntax:
        Integer keys (0, 1, -1)    -> Update value at index
        "[start:stop:step]"        -> Replace slice with new values
        "[:]"                      -> Replace entire list
        "[]"                       -> Extend list at end (special case)

    Python list natively supports slice-based modification:
        a = [1, 2, 3]
        a[:0] = [0]      # a is [0, 1, 2, 3] (prepend)
        a[1:3] = []      # Delete elements at [1:3]
        a[2:2] = [10]    # Insert at position 2

    Examples
    --------
    >>> ListDSL.parse("[:]")  # doctest: +NORMALIZE_WHITESPACE
    ListDSL(operation=<ListOperation.SLICE: 'slice'>,
            slice_obj=slice(None, None, None), index=None)
    >>> ListDSL.parse("[:0]")  # doctest: +NORMALIZE_WHITESPACE
    ListDSL(operation=<ListOperation.SLICE: 'slice'>,
            slice_obj=slice(None, 0, None), index=None)
    >>> ListDSL.parse("[1:3]")  # doctest: +NORMALIZE_WHITESPACE
    ListDSL(operation=<ListOperation.SLICE: 'slice'>,
            slice_obj=slice(1, 3, None), index=None)
    >>> ListDSL.parse("[]")
    ListDSL(operation=<ListOperation.SLICE: 'slice'>, slice_obj=None, index=None)
    """

    # Pattern for DSL: [start:stop:step], [], [N], [-N]
    # Matches: [N], [-N], [N:M], [:M], [N:], [:], [N:M:S], []
    _PATTERN = re.compile(
        r"^\[(?:(?P<index>-?\d+)|(?P<start>-?\d*):(?P<stop>-?\d*)?(?::(?P<step>-?\d*))?)?\]$",
    )

    operation: ListOperation
    slice_obj: slice | None = None  # None means extend at end ([])
    index: int | None = None  # For UPDATE operation

    @classmethod
    def parse(cls, key_str: str | int) -> ListDSL | None:
        """Parse DSL pattern or integer index from key string.

        Handles:
        - Slice notation: '[:]', '[:0]', '[N:M]', '[N:M:S]'
        - Append: '[]'
        - Integer indices: '[0]', '[1]', '[-1]' (bracket-wrapped)
        - Plain integers: '0', '1', '-1', 0, 1, -1

        Parameters
        ----------
        key_str : str | int
            Key string or integer to parse

        Returns
        -------
        ListDSL | None
            Parsed DSL command, or None if not recognized

        Raises
        ------
        ValueError
            If DSL pattern is invalid
        """
        # Convert to string for consistent processing
        key_str = str(key_str)

        # Try matching bracket patterns first
        match = cls._PATTERN.match(key_str)

        if match is not None:
            # Extract match groups
            groups = match.groupdict()

            # Check if it's [N] format (single integer captured by index group)
            index_str = groups.get("index")
            if index_str is not None:
                return cls(ListOperation.UPDATE, index=int(index_str))

            # Otherwise it's a slice pattern
            start_str = groups.get("start") or ""
            stop_str = groups.get("stop") or ""
            step_str = groups.get("step") or ""

            # Check for empty brackets [] - special case for extend
            if (
                start_str == ""
                and stop_str == ""
                and step_str == ""
                and ":" not in key_str
            ):
                return cls(ListOperation.SLICE, slice_obj=None)

            # Convert to integers for slice (empty string means None)
            start = int(start_str) if start_str else None
            stop = int(stop_str) if stop_str else None
            step = int(step_str) if step_str else None

            return cls(ListOperation.SLICE, slice_obj=slice(start, stop, step))

        # Not a bracket pattern - try as plain integer
        try:
            index = int(key_str)
            return cls(ListOperation.UPDATE, index=index)
        except ValueError:
            # Not recognized as any valid pattern
            return None

    @classmethod
    def from_key(
        cls,
        key: str | int,
        lst: MutableSequence[Any],
        default: Any,
    ) -> tuple[ListDSL, Any]:
        """Create ListDSL from key and return value to use.

        Delegates parsing to parse() method and validates integer indices.

        Parameters
        ----------
        key : str | int
            Key that could be slice DSL pattern or integer index.
            Accepts: int (0, 1, -1), str with int ('[0]', '[1]', '[-1]'),
            or slice notation ('[:]', '[:0]', '[N:M]', '[]')
        lst : MutableSequence[Any]
            The list being updated
        default : Any
            Default value to use for new items

        Returns
        -------
        tuple[ListDSL, object]
            (ListDSL instance, value to use for merging)

        Raises
        ------
        ValueError
            If key is invalid (not DSL pattern or integer)
        IndexError
            If integer index is out of range
        """
        # Delegate parsing to parse()
        dsl = cls.parse(key)

        if dsl is None:
            msg = (
                f"Invalid list key: {key!r}. Use integer index or slice notation "
                f"('[:]', '[:0]', '[N:M]', '[]')"
            )
            raise ValueError(msg)

        # For UPDATE operations (integer indices), validate range and get existing value
        if dsl.operation == ListOperation.UPDATE:
            assert dsl.index is not None  # UPDATE operation always has index
            try:
                existing_value = lst[dsl.index]
            except IndexError as e:
                msg = f"List index {dsl.index} out of range (length: {len(lst)})"
                raise IndexError(msg) from e
            else:
                return dsl, existing_value

        # For SLICE operations, return default value
        return dsl, default

    def apply(self, lst: MutableSequence[Any], value: Any) -> bool:
        """Apply operation to list.

        Parameters
        ----------
        lst : MutableSequence[Any]
            The list to modify
        value : Any
            The value to apply

        Returns
        -------
        bool
            True if this was a slice operation (no further merging needed),
            False if this was an UPDATE operation (may need further merging)
        """
        if self.operation == ListOperation.SLICE:
            # Handle slice assignment
            if self.slice_obj is None:
                # Special case: [] means extend at end
                slice_obj = slice(len(lst), len(lst))
            else:
                slice_obj = self.slice_obj

            # Wrap scalar as sequence for slice assignment
            if not isinstance(value, ST):
                value = [value]
            lst[slice_obj] = value
            return True  # Slice operation complete, no merging

        # UPDATE operation - don't modify list here, just return False
        # The value will be merged in rupdate
        return False  # May need merging

    def to_slice(self, list_length: int) -> slice:
        """Convert DSL operation to slice for list access.

        Parameters
        ----------
        list_length : int
            Current length of the list being updated

        Returns
        -------
        slice
            Slice object for list modification
        """
        if self.slice_obj is None:
            # Special case: [] means extend at end
            return slice(list_length, list_length)
        return self.slice_obj


def rupdate(
    d: MutableMapping[Any, Any] | MutableSequence[Any],
    u: Mapping[Any, Any],
    *,
    copy_subdict: bool = True,
) -> None:
    r"""Update dict recursively.

    This will update `d` with items in `u` in a recursive fashion.

    `d` can be either list or dict. `u` has to be dict where int
    keys can be used to identify list items.

    When updating list, slice notation in brackets can be used for
    slice-based modifications following Python's native list slice syntax.

    Parameters
    ----------
    d : dict, list
        The container to be updated

    u : dict
        The update dict.

    copy_subdict : bool
        If True, subdicts in `u` will get copied to `d`, such that
        further change in `d` will not propagate back to `u`.

    Returns
    -------
    None
        Dict `d` is updated in place.

    List DSL Syntax
    ---------------
    Integer keys (0, 1, -1):
        Update value at index (e.g., {0: 'new'} replaces first item)

    Slice notation keys:
        "[:]"      : Replace entire list
        "[:0]"     : Prepend to list
        "[N:M]"    : Replace slice [N:M] (empty list deletes elements)
        "[N:N]"    : Insert at position N
        "[]"       : Extend list at end (special case)

    Chaining Operations:
        Multiple operations can be combined in a single rupdate call.
        Operations are applied in dict iteration order (Python 3.7+).
        Index-based operations refer to the current state after previous
        operations have been applied.

    Examples
    --------
    >>> d = {"items": [1, 2, 3]}
    >>> rupdate(d, {"items": {"[]": 4}})  # Extend at end
    >>> d["items"]
    [1, 2, 3, 4]

    >>> d = {"items": [1, 2, 3]}
    >>> rupdate(d, {"items": {"[:0]": 0}})  # Prepend
    >>> d["items"]
    [0, 1, 2, 3]

    >>> d = {"items": [1, 2, 3, 4]}
    >>> rupdate(d, {"items": {"[1:3]": [10, 20]}})  # Replace slice
    >>> d["items"]
    [1, 10, 20, 4]

    >>> d = {"items": [1, 2, 3, 4]}
    >>> rupdate(d, {"items": {"[1:3]": []}})  # Delete slice
    >>> d["items"]
    [1, 4]

    >>> d = {"items": [1, 2, 3]}
    >>> rupdate(d, {"items": {0: 10}})  # Update at index
    >>> d["items"]
    [10, 2, 3]

    >>> d = {"items": [1, 2, 3]}
    >>> rupdate(d, {"items": {"[]": [4, 5], -1: 10}})  # Chain: extend then update
    >>> d["items"]
    [1, 2, 3, 4, 10]

    Notes
    -----
    Follows Python's native list slice assignment behavior.

    **Operation Ordering**: Since Python 3.7+, dict insertion order is preserved.
    Operations are applied in the order they appear in the update dict. When
    chaining operations, index-based operations (like -1) refer to the list
    state after previous operations have been applied.

    See [1]_.

    .. [1] https://stackoverflow.com/a/52099238/1824372

    """
    stack = [(d, u)]

    while stack:
        # here d can only be list or dict
        d, u = stack.pop(0)
        for k, v in u.items():
            # determine default for new subdicts
            # when copy_subdict is True, we create new dicts for subdicts in u
            # when copy_subdict is False, we assign subdicts in u directly
            default = {} if copy_subdict else None
            if isinstance(d, MT):
                # handle d as dict
                dv = d.setdefault(k, default)  # ty: ignore[no-matching-overload]
            elif isinstance(d, ST):
                # handle d as list - use ListDSL for all list key handling
                dsl, dv = ListDSL.from_key(k, d, default)

                # Apply operation and check if merging is needed
                if dsl.apply(d, v):
                    # Slice operation - no further merging needed
                    continue

                # UPDATE operation - dsl.index has the index, dv has current value
                # We'll use dsl.index as k for the merging logic below
                assert dsl.index is not None  # UPDATE operation always has index
                k = dsl.index  # noqa: PLW2901
            else:
                msg = f"Cannot update {type(d).__name__} with rupdate"
                raise TypeError(msg)

            # now dv is the current value at the key
            if not isinstance(v, MT):
                # u[k] is not a dict, nothing to merge, so just set it
                d[k] = v
                continue

            # now v = u[k] is dict
            if not isinstance(dv, MT | ST):
                # d[k] is not a container, so just set it to u[k]
                d[k] = v
            else:
                # both d[k] and u[k] are containers, push them on the stack
                # to merge further
                stack.append((dv, v))


def dict_product(**kwargs: Any) -> Any:
    """Return the Cartesian product of dicts."""
    return (
        dict(zip(kwargs.keys(), x, strict=False))
        for x in itertools.product(*kwargs.values())
    )


def dict_from_flat_dict(dct: dict[str, Any]) -> dict[str, Any]:
    """Convert flat dict with dotted keys to nested dict structure.

    Uses rupdate to merge each key one at a time, handling conflicts
    automatically through rupdate's merging logic.

    Examples
    --------
    >>> dict_from_flat_dict({'a.b': 1, 'a.c': 2})
    {'a': {'b': 1, 'c': 2}}

    >>> dict_from_flat_dict({'items.0': 1, 'items.1': 2})
    {'items': {'0': 1, '1': 2}}

    Parameters
    ----------
    dct : dict
        Flat dictionary with dotted keys

    Returns
    -------
    dict
        Nested dict with rupdate DSL patterns applied
    """
    result = {}

    for key, value in dct.items():
        # Split on dots to create nested structure
        parts = key.split(".")

        # Build nested dict for this key
        nested = {}
        current = nested
        for part in parts[:-1]:
            current[part] = {}
            current = current[part]
        current[parts[-1]] = value

        # Merge using rupdate (handles ListDSL automatically)
        rupdate(result, nested)

    return result


def dict_to_flat_dict(  # noqa: C901
    dct: dict[str, Any],
    key_prefix: str = "",
    *,
    list_index_as_key: bool = False,
) -> dict[str, Any]:
    """Return dict from dict with nested dicts."""

    def _dk(key):
        return f".{key}"

    def _lk(i):
        if list_index_as_key:
            return _dk(i)
        return f"[{i}]"

    def _nested_kvs(data: dict | list) -> list | tuple:
        if isinstance(data, list | dict):
            kvs = []
            if isinstance(data, list):
                items = ((_lk(i), data[i]) for i in range(len(data)))
            else:
                items = ((_dk(key), data[key]) for key in data)
            for key, value in items:
                result = _nested_kvs(value)
                if isinstance(result, list):
                    if isinstance(value, dict | list):
                        kvs.extend([(f"{key}{item}", val) for (item, val) in result])
                elif isinstance(result, tuple):
                    kvs.append((f"{key}", result[1]))
                else:
                    pass
            return kvs
        # leaf
        return (None, data)

    if not isinstance(dct, dict):
        msg = "only dict is allowed as input."
        raise TypeError(msg)
    kvs = _nested_kvs(dct)
    # build the dict
    result = {}
    for k, v in kvs:
        _k = key_prefix + k.lstrip(".")
        result[_k] = v
    return result


def add_to_dict(d: MutableMapping, key: Any, *, exist_ok: bool = True) -> Any:
    """Return a decorator to add decorated item to dict.

    When key is callable, it generate the actual key by
    invoking it with the decorated item.
    """

    def decorator(thing: Any) -> Any:
        _key = key(thing) if callable(key) else key
        if not exist_ok and _key in d:
            msg = f"key={_key} exist."
            raise ValueError(msg)
        d[_key] = thing
        return thing

    return decorator


def dict_from_regex_match(
    pattern: str | re.Pattern,
    string: str,
    type_dispatcher: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a dict from matching `pattern` to `string`.

    If match failed, returns None.

    Parameters
    ----------
    pattern : str, `re.Pattern`
        The regex that matches to the `input_`.

    input_ : str
        The string to be matched.

    type_dispatcher : dict
        This specifies how the matched group values are handled after being
        extracted.
    """
    if type_dispatcher is None:
        type_dispatcher = {}
    m = re.match(pattern, string)
    if m is None:
        return None

    result = {}
    for k, v in m.groupdict().items():
        if k in type_dispatcher and v is not None:
            result[k] = type_dispatcher[k](v)
        else:
            result[k] = v
    return result
