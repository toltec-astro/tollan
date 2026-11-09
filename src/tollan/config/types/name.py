"""Pydantic annotations for names used as keys, filenames and identifiers."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

__all__ = ["PathSegment", "SafeName", "SafeNamePath"]


def _validate_path_segment(value: str) -> str:
    if not value or value in {".", ".."} or any(c in value for c in "/\\\x00"):
        msg = f"Expected one path segment: {value!r}"
        raise ValueError(msg)
    return value


type PathSegment = Annotated[str, AfterValidator(_validate_path_segment)]
"""One nonempty file or directory name, excluding dot references, separators and NUL.

Preserves spelling, including spaces, Unicode, colons and leading punctuation.
"""

_SAFE_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]*"

type SafeName = Annotated[str, StringConstraints(pattern=rf"^{_SAFE_NAME}$")]
"""A name usable unquoted as a key, filename, argument or host name.

ASCII letters, digits, ``_``, ``.`` and ``-``, starting with a letter or digit.
"""

type SafeNamePath = Annotated[
    str,
    StringConstraints(pattern=rf"^(?:{_SAFE_NAME}:)?{_SAFE_NAME}(?:/{_SAFE_NAME})*$"),
]
"""``/``-separated SafeName components, with an optional ``qualifier:`` prefix.

Examples are ``reports``, ``reports/2024`` and ``mirror:reports/2024``.
"""
