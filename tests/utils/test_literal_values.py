"""Literal value extraction."""

from enum import Enum
from typing import Literal

import pytest

from tollan.utils.typing import get_literal_value, get_literal_values

type TextT = str


class Format(Enum):
    csv = "csv"
    json = "json"


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (Literal["csv", "json"], ["csv", "json"]),
        (Literal["csv"], ["csv"]),
        (Literal[1, 2], [1, 2]),
        (Literal[False, 0, True, 1], [False, 0, True, 1]),
        (Literal[None], [None]),  # noqa: PYI061 -- Test literal introspection.
        (Literal[b"csv"], [b"csv"]),
        (Literal[Format.csv, Format.json], [Format.csv, Format.json]),
    ],
)
def test_literal_values(annotation, expected):
    values = get_literal_values(annotation)
    assert values == expected
    assert [type(value) for value in values] == [type(value) for value in expected]


def test_named_aliases():
    type FormatT = Literal["csv", "json"]
    type AliasT = FormatT

    assert get_literal_values(FormatT) == ["csv", "json"]
    assert get_literal_values(AliasT) == ["csv", "json"]


def test_class_alias():
    class Settings:
        type FormatT = Literal["csv"]

    assert get_literal_values(Settings.FormatT) == ["csv"]
    assert get_literal_value(Settings.FormatT) == "csv"


def test_nested_literal_aliases_are_deduplicated():
    type TextT = Literal["csv", "json"]
    type FormatT = Literal[TextT, "csv", "parquet"]

    assert get_literal_values(FormatT) == ["csv", "json", "parquet"]


def test_results_are_independent():
    type FormatT = Literal["csv", "json"]

    values = get_literal_values(FormatT)
    values.append("parquet")
    assert get_literal_values(FormatT) == ["csv", "json"]


@pytest.mark.parametrize("annotation", [str, list[str], Literal, TextT])
def test_non_literal_rejected(annotation):
    with pytest.raises(TypeError, match="Expected a Literal"):
        get_literal_values(annotation)


def test_invalid_literal_value_rejected():
    annotation = Literal[object()]  # ty: ignore[invalid-type-form]
    with pytest.raises(TypeError, match="not a valid literal value"):
        get_literal_values(annotation)


def test_recursive_alias_rejected():
    type RecursiveT = RecursiveT  # ty: ignore[cyclic-type-alias-definition]

    with pytest.raises(TypeError, match="Recursive alias"):
        get_literal_values(RecursiveT)


def test_sole_literal_value():
    assert get_literal_value(Literal["csv"]) == "csv"
    assert get_literal_value(Literal[None]) is None  # noqa: PYI061


def test_sole_literal_value_requires_exactly_one():
    with pytest.raises(ValueError, match="exactly one literal value"):
        get_literal_value(Literal["csv", "json"])
