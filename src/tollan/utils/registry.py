"""Keyed registration and lookup."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["Registry"]


class Registry[KeyT: Hashable, ValueT](Mapping[KeyT, ValueT]):
    """A mapping populated through registration of unique keys.

    Register entries with `register`. Lookup and iteration include subsequent
    registrations, in insertion order. Item assignment and deletion are not
    supported. Values are retained as supplied, without copying or validation.

    Examples
    --------
    >>> registry = Registry[str, int]()
    >>> registry.register("first", 1)
    >>> registry["first"]
    1
    >>> registry.register("first", 1)
    Traceback (most recent call last):
    ...
    ValueError: Key already registered: 'first'
    """

    def __init__(self) -> None:
        self._entries: dict[KeyT, ValueT] = {}

    def __getitem__(self, key: KeyT) -> ValueT:
        return self._entries[key]

    def __iter__(self) -> Iterator[KeyT]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def register(self, key: KeyT, value: ValueT) -> None:
        """Add an entry under an unused key.

        Parameters
        ----------
        key : hashable
            Key used to look up the entry.
        value : object
            Value to register.

        Raises
        ------
        ValueError
            The key already exists, including when its value is the same object.
            The existing entry remains unchanged.
        """
        if key in self._entries:
            msg = f"Key already registered: {key!r}"
            raise ValueError(msg)
        self._entries[key] = value
