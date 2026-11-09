"""Tests for name annotations."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from tollan.config.types import SafeName, SafeNamePath


@pytest.mark.spec("scientific-value-types")
@pytest.mark.parametrize("value", ["cpu1", "transform", "login.example.org", "a-b"])
def test_safe_name_accepts_identifiers(value):
    assert TypeAdapter(SafeName).validate_python(value) == value


@pytest.mark.spec("scientific-value-types")
@pytest.mark.parametrize(
    "value",
    ["", ".hidden", "-flag", "_x", "..", "a/b", "a b", "mirror:reports", "café"],
)
def test_safe_name_rejects_unsafe_names(value):
    with pytest.raises(ValidationError):
        TypeAdapter(SafeName).validate_python(value)


@pytest.mark.spec("scientific-value-types")
@pytest.mark.parametrize(
    "value",
    [
        "reports",
        "reports/2024",
        "mirror:reports",
        "mirror:reports-v2",
        "mirror:reports/2024",
    ],
)
def test_safe_name_path_accepts_qualified_paths(value):
    assert TypeAdapter(SafeNamePath).validate_python(value) == value


@pytest.mark.spec("scientific-value-types")
@pytest.mark.parametrize(
    "value",
    [
        "",
        "/reports",
        "reports/",
        "reports//2024",
        "reports/../2024",
        "a:b:c",
        "reports/x:2024",
        ":reports",
        "a b",
    ],
)
def test_safe_name_path_rejects_malformed_paths(value):
    with pytest.raises(ValidationError):
        TypeAdapter(SafeNamePath).validate_python(value)
