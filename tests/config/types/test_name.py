"""Tests for name annotations."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from tollan.config.types import SafeName, SafeNamePath


@pytest.mark.parametrize("value", ["cpu1", "reduce_obs", "login.example.org", "a-b"])
def test_safe_name_accepts_identifiers(value):
    assert TypeAdapter(SafeName).validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    ["", ".hidden", "-flag", "_x", "..", "a/b", "a b", "taco:ql", "café"],
)
def test_safe_name_rejects_unsafe_names(value):
    with pytest.raises(ValidationError):
        TypeAdapter(SafeName).validate_python(value)


@pytest.mark.parametrize(
    "value", ["ql", "taco/ql", "taco:ql", "taco:ql-main", "unity:taco/ql"]
)
def test_safe_name_path_accepts_qualified_paths(value):
    assert TypeAdapter(SafeNamePath).validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "/ql", "ql/", "taco//ql", "taco/../ql", "a:b:c", "taco/x:ql", ":ql", "a b"],
)
def test_safe_name_path_rejects_malformed_paths(value):
    with pytest.raises(ValidationError):
        TypeAdapter(SafeNamePath).validate_python(value)
