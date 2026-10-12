"""Behavioral contracts for string-selector configuration fields."""

from __future__ import annotations

import json
import pickle
import re

import pytest
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from tollan.config import FrozenBaseModel
from tollan.config.types import StringSelector


class Settings(FrozenBaseModel):
    names: StringSelector


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([".", "raw"], ["raw", ".", "raw"]),
        ({"includes": [".", "raw"]}, ["raw", ".", "raw"]),
        ({"excludes": [".", "raw"]}, ["other", "raw/a", "RAW"]),
        ({"pattern": "raw(/.*)?"}, ["raw", "raw/a", "raw"]),
        ("raw(/.*)?", ["raw", "raw/a", "raw"]),
        ([], []),
        ({"includes": []}, []),
        ({"excludes": []}, ["other", "raw", ".", "raw/a", "RAW", "raw"]),
    ],
)
def test_select_preserves_candidate_order_and_duplicates(value, expected):
    selector = Settings(names=value).names
    candidates = ["other", "raw", ".", "raw/a", "RAW", "raw"]

    assert selector.select(iter(candidates)) == expected
    assert [name for name in candidates if selector.matches(name)] == expected
    pattern = selector.as_regex()
    assert [name for name in candidates if pattern.fullmatch(name)] == expected


def test_exact_items_have_no_pattern_or_path_semantics():
    selector = StringSelector.model_validate([".", "*", "a/b", "", " x ", "[ab]"])

    assert selector.select(["x", "a", "b", "a//b", "./a/b", "a/b/c"]) == []
    assert selector.select([".", "*", "a/b", "", " x ", "[ab]"]) == [
        ".",
        "*",
        "a/b",
        "",
        " x ",
        "[ab]",
    ]


def test_regex_is_fullmatch_and_retains_python_regex_semantics():
    selector = StringSelector.model_validate({"pattern": "raw"})
    assert selector.select(["raw", "raw/a", "draw", "RAW", "raw\n"]) == ["raw"]
    selector = StringSelector.model_validate({"pattern": "(?i)raw"})
    assert selector.select(["RAW", "raw"]) == ["RAW", "raw"]


def test_select_evaluates_current_candidates_not_a_registry_snapshot():
    selector = StringSelector.model_validate({"excludes": ["experimental"]})
    candidates = ["builtin", "experimental"]
    assert selector.select(candidates) == ["builtin"]

    candidates.append("extension")
    assert selector.select(candidates) == ["builtin", "extension"]


@pytest.mark.parametrize(
    "value",
    [
        [],
        [""],
        [".", "a|b", "x(y)", "a\\b", "raw", "raw", "", "raw\n"],
        {"excludes": []},
        {"excludes": [""]},
        {"excludes": [".", "a|b", "x(y)", "a\\b", "raw", "", "raw\n"]},
        "(?i)raw(?:/.*)?",
        {"pattern": re.compile(r"raw.*", re.IGNORECASE | re.DOTALL)},
    ],
)
def test_regex_export_preserves_selection_for_arbitrary_strings(value):
    selector = StringSelector.model_validate(value)
    pattern = selector.as_regex()
    candidates = [
        "",
        ".",
        "a",
        "b",
        "a|b",
        "x(y)",
        "xy",
        "a\\b",
        "raw",
        "RAW",
        "raw/scan",
        "raw\n",
        "raw\nscan",
        "other\n",
        "\n",
        "λ",
    ]
    assert [name for name in candidates if pattern.fullmatch(name)] == selector.select(
        candidates
    )


def test_regex_export_retains_an_existing_pattern_and_flags():
    pattern = re.compile("raw.*", re.IGNORECASE | re.DOTALL)
    selector = StringSelector.model_validate({"pattern": pattern})
    assert selector.as_regex() is pattern


def test_string_shorthand_is_regex_not_an_exact_name():
    assert StringSelector.model_validate(".").select([".", "x", "xx"]) == [".", "x"]
    assert StringSelector.model_validate(["."]).select([".", "x", "xx"]) == ["."]
    assert StringSelector.model_validate("").select(["", "x"]) == [""]


@pytest.mark.parametrize(
    "value",
    [
        "[",
        None,
        1,
        True,
        ("raw",),
        {"raw"},
        {},
        {"includes": [], "excludes": []},
        {"includes": [], "pattern": ".*"},
        {"excludes": [], "pattern": ".*"},
        {"includes": [], "typo": []},
        {"match": ".*"},
        {"includes": "raw"},
        {"excludes": ("raw",)},
        {"includes": [1]},
        {"excludes": [None]},
        [b"raw"],
        [{"pattern": "raw.*"}],
        {"includes": [{"pattern": "raw.*"}]},
        {"pattern": ["raw"]},
        {"pattern": b"raw"},
        {"pattern": "["},
        {"pattern": None},
    ],
)
def test_invalid_forms_are_rejected_by_the_field(value):
    with pytest.raises(ValidationError):
        Settings.model_validate({"names": value})


@pytest.mark.parametrize(
    "value",
    [
        [".", "raw"],
        {"excludes": ["raw"]},
        {"pattern": "(?i)raw(/.*)?"},
        "(?i)raw(/.*)?",
    ],
)
def test_explicit_mapping_serialization_and_config_roundtrip(value):
    settings = Settings.model_validate({"names": value})
    normalized = {"includes": value} if isinstance(value, list) else value
    if isinstance(value, str):
        normalized = {"pattern": value}
    assert settings.model_dump(mode="json") == {"names": normalized}
    assert json.loads(settings.model_dump_json()) == {"names": normalized}
    assert Settings.model_validate_json(settings.model_dump_json()) == settings
    assert Settings.model_validate_yaml(settings.model_dump_yaml()) == settings
    assert pickle.loads(pickle.dumps(settings)) == settings  # noqa: S301 -- trusted test data


def test_field_works_with_ordinary_models_and_type_adapter():
    class Model(BaseModel):
        names: StringSelector

    adapter = TypeAdapter(StringSelector)
    selector = adapter.validate_python(["raw"])
    assert Model(names=["raw"]).names == selector
    assert adapter.validate_json('["raw"]') == selector
    assert adapter.validate_json(adapter.dump_json(selector)) == selector
    assert StringSelector.model_validate(selector) is selector
    with pytest.raises(ValidationError):
        Model(names=[1])


def test_selector_and_declared_defaults_follow_frozen_config_contract():
    class Defaults(FrozenBaseModel):
        names: StringSelector = Field(default={"excludes": []})

    assert Defaults().names.matches("anything")
    selector = Settings(names=["raw"]).names
    with pytest.raises(ValidationError, match="frozen"):
        selector.root = {"excludes": []}
    with pytest.raises(ValidationError, match="frozen"):
        selector.root.includes = []


def test_json_schema_distinguishes_input_shorthand_from_normalized_output():
    adapter = TypeAdapter(StringSelector)
    validation = adapter.json_schema(mode="validation")
    serialization = adapter.json_schema(mode="serialization")

    for schema in (validation, serialization):
        nodes = [schema, *schema["$defs"].values()]
        accepts_list = any(
            branch.get("type") == "array"
            for node in nodes
            for branch in node.get("anyOf", [])
        )
        assert accepts_list is (schema is validation)
        accepts_string = any(
            branch.get("type") == "string"
            for node in nodes
            for branch in node.get("anyOf", [])
        )
        assert accepts_string is (schema is validation)
        modes = [node for node in nodes if node.get("type") == "object"]
        assert {tuple(mode["required"]) for mode in modes} == {
            ("includes",),
            ("excludes",),
            ("pattern",),
        }
        assert all(mode["additionalProperties"] is False for mode in modes)
