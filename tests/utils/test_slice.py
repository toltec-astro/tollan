"""Tests for slice parsing and sequence selection."""

from __future__ import annotations

import pytest
from astropy.table import Table

from tollan.utils.slice import parse_slice


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", slice(None)),
        (":", slice(None)),
        ("::", slice(None)),
        (":10", slice(None, 10)),
        ("1:", slice(1, None)),
        ("1:10", slice(1, 10)),
        ("1:10:", slice(1, 10)),
        ("1:10:2", slice(1, 10, 2)),
        ("1::2", slice(1, None, 2)),
        ("::2", slice(None, None, 2)),
        ("::-1", slice(None, None, -1)),
        ("-5:-1:2", slice(-5, -1, 2)),
        ("+1:+10:+2", slice(1, 10, 2)),
        ("0", slice(0, 1)),
        ("7", slice(7, 8)),
        ("+7", slice(7, 8)),
        ("-1", slice(-1, None)),
        ("-3", slice(-3, -2)),
    ],
)
def test_parse_slice(text, expected):
    assert parse_slice(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "[]",
        "[1:3]",
        "*",
        "{1,3}",
        "1,3",
        "1-2",
        "1+2",
        "1:2:3:4",
        "1:::2",
        "1.5:3",
        "1e2",
        "+",
        "-",
        "1:-",
        "1:2:-",
        " 1:3 ",
        "1: 3",
        "1:3\n",
    ],
)
def test_parse_slice_rejects_malformed_text(text):
    with pytest.raises(ValueError, match="Invalid slice"):
        parse_slice(text)


@pytest.mark.parametrize("text", ["::0", "1:5:0", "1:5:-0", "1:5:+0"])
def test_parse_slice_rejects_zero_step(text):
    with pytest.raises(ValueError, match="step cannot be zero"):
        parse_slice(text)


@pytest.mark.parametrize("value", [None, 1, True, slice(None), b"1:3"])
def test_parse_slice_requires_text(value):
    with pytest.raises(TypeError):
        parse_slice(value)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (":10", [0, 1, 2, 3, 4]),
        ("-1", [4]),
        ("-3", [2]),
        ("9", []),
        ("-9", []),
        ("::-1", [4, 3, 2, 1, 0]),
        ("4:0:-2", [4, 2]),
        ("3:1", []),
    ],
)
def test_parse_slice_applies_and_resolves_to_indices(text, expected):
    values = list(range(5))
    selection = parse_slice(text)
    assert values[selection] == expected
    assert list(range(*selection.indices(len(values)))) == expected


@pytest.mark.parametrize(("text", "expected"), [("1", 20), ("-1", 30)])
def test_parse_slice_preserves_one_row_table(text, expected):
    table = Table({"value": [10, 20, 30]})
    selected = table[parse_slice(text)]
    assert isinstance(selected, Table)
    assert selected["value"].tolist() == [expected]
