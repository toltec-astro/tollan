"""Selectors for exact string values or regular-expression matches."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, ConfigDict, RootModel

from ..base import FrozenBaseModel

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["StringSelector"]


class _IncludeList(FrozenBaseModel):
    model_config = ConfigDict(extra="forbid")

    includes: list[str]


class _ExcludeList(FrozenBaseModel):
    model_config = ConfigDict(extra="forbid")

    excludes: list[str]


class _RegexPattern(FrozenBaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: re.Pattern[str]


type _SelectorValue = _IncludeList | _ExcludeList | _RegexPattern


def _prepare_selector(value: Any) -> Any:
    """Expand shorthand before validating the selection mode."""
    if isinstance(value, str):
        return {"pattern": value}
    if isinstance(value, list):
        return {"includes": value}
    return value


class StringSelector(RootModel, FrozenBaseModel):
    """Select strings by exact inclusion, exact exclusion, or regex fullmatch.

    Accepts a regex string, a list of exact values, or a mapping containing
    exactly one of ``includes``, ``excludes``, and ``pattern``. Inclusion and
    exclusion values are lists of literal, case-sensitive strings. A pattern
    uses Python regular expressions and must match the entire candidate string.
    Mixed modes are invalid.

    An empty inclusion list selects nothing; an empty exclusion list selects
    everything. String and list shorthand serialize as explicit ``pattern``
    and ``includes`` mappings. Selection does not normalize strings or access
    the filesystem.

    Examples
    --------
    >>> from tollan.config import FrozenBaseModel
    >>> class Settings(FrozenBaseModel):
    ...     names: StringSelector
    >>> settings = Settings(names=[".", "raw"])
    >>> settings.names.select(["raw", "other", "."])
    ['raw', '.']
    >>> settings.model_dump(mode="json")
    {'names': {'includes': ['.', 'raw']}}
    >>> StringSelector.model_validate({"excludes": ["raw"]}).matches("other")
    True
    >>> StringSelector.model_validate({"pattern": "raw(/.*)?"}).matches("raw/a")
    True
    """

    root: Annotated[
        _SelectorValue,
        BeforeValidator(
            _prepare_selector, json_schema_input_type=str | list[str] | _SelectorValue
        ),
    ]

    def as_regex(self) -> re.Pattern[str]:
        """Create an equivalent regex for use with ``fullmatch()``.

        Returns
        -------
        re.Pattern[str]
            Pattern whose ``fullmatch(value)`` succeeds exactly when
            ``matches(value)`` is true. Exact values are escaped; an existing
            regex is returned unchanged, including its flags.

        Examples
        --------
        >>> pattern = StringSelector.model_validate([".", "raw"]).as_regex()
        >>> pattern.fullmatch(".") is not None
        True
        >>> pattern.fullmatch("raw/scan") is None
        True
        """
        rule = self.root
        if isinstance(rule, _RegexPattern):
            return rule.pattern
        if isinstance(rule, _IncludeList):
            if not rule.includes:
                return re.compile(r"(?!)")
            return re.compile("|".join(map(re.escape, rule.includes)))
        if not rule.excludes:
            return re.compile(r"[\s\S]*")
        excluded = "|".join(map(re.escape, rule.excludes))
        return re.compile(rf"(?!(?:{excluded})\Z)[\s\S]*")

    def matches(self, value: str) -> bool:
        """Test whether a string is selected.

        Parameters
        ----------
        value : str
            Candidate string, used without normalization.

        Returns
        -------
        bool
            Whether the string satisfies the selector.
        """
        rule = self.root
        if isinstance(rule, _IncludeList):
            return value in rule.includes
        if isinstance(rule, _ExcludeList):
            return value not in rule.excludes
        return rule.pattern.fullmatch(value) is not None

    def select(self, values: Iterable[str]) -> list[str]:
        """Filter strings while preserving their order and duplicates.

        Parameters
        ----------
        values : iterable of str
            Candidate strings. The iterable is consumed once.

        Returns
        -------
        list of str
            Selected strings in their original order.
        """
        return [value for value in values if self.matches(value)]
