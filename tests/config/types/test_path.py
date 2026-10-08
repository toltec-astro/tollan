"""Tests for context-aware Pydantic path annotations."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from tollan.config import FrozenBaseModel
from tollan.config.types import (
    AbsAnyPath,
    AbsDirectoryPath,
    AbsFilePath,
    AnyPath,
    path_field,
)


def test_path_root_context_and_json_roundtrip(tmp_path: Path) -> None:
    """Relative inputs resolve against context and serialize as JSON strings."""
    data_file = tmp_path / "data.nc"
    data_file.touch()
    adapter = TypeAdapter(AbsFilePath)

    value = adapter.validate_python("data.nc", context={"rootpath": tmp_path})
    loaded = adapter.validate_json(adapter.dump_json(value))

    assert value == data_file.resolve()
    assert loaded == value
    assert adapter.json_schema() == {"format": "file-path", "type": "string"}


def test_path_resolution_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aliases retain their documented resolution and existence behavior."""
    monkeypatch.chdir(tmp_path)
    assert TypeAdapter(AnyPath).validate_python("relative") == Path("relative")
    assert (
        TypeAdapter(AbsAnyPath).validate_python("relative")
        == (tmp_path / "relative").resolve()
    )
    assert TypeAdapter(AbsDirectoryPath).validate_python(tmp_path) == tmp_path.resolve()


def test_path_context_propagates_to_nested_models() -> None:
    """Retain nested root-context coverage from the pre-v3 type tests."""

    class Nested(FrozenBaseModel):
        path: AbsAnyPath = Path("a")

    class Container(FrozenBaseModel):
        nested: list[Nested]

    model = Container.model_validate(
        {"nested": [{}, {"path": "b"}]},
        context={"rootpath": "~"},
    )

    assert model.nested[0].path == Path("~/a").expanduser().resolve()
    assert model.nested[1].path == Path("~/b").expanduser().resolve()


@pytest.mark.parametrize(
    ("field_type", "value", "error_type"),
    [
        (AnyPath, object(), "path_type"),
        (AbsAnyPath, object(), "path_type"),
        (AbsFilePath, "missing", "path_not_file"),
        (AbsDirectoryPath, "missing", "path_not_directory"),
    ],
)
def test_path_stable_validation_errors(field_type, value, error_type):
    """Invalid user values are reported as coded ValidationErrors."""
    with pytest.raises(ValidationError) as exc_info:
        TypeAdapter(field_type).validate_python(value)
    assert exc_info.value.errors()[0]["type"] == error_type


def test_path_file_directory_and_new_constraints(tmp_path: Path) -> None:
    """Public Pydantic path types supply their standard constraint errors."""
    data_file = tmp_path / "data.nc"
    data_file.touch()

    with pytest.raises(ValidationError) as exc_info:
        TypeAdapter(AbsFilePath).validate_python(tmp_path)
    assert exc_info.value.errors()[0]["type"] == "path_not_file"

    with pytest.raises(ValidationError) as exc_info:
        TypeAdapter(AbsDirectoryPath).validate_python(data_file)
    assert exc_info.value.errors()[0]["type"] == "path_not_directory"

    new_path_type = path_field(path_type="new")
    adapter = TypeAdapter(new_path_type)
    assert (
        adapter.validate_python(tmp_path / "new.nc") == (tmp_path / "new.nc").resolve()
    )

    with pytest.raises(ValidationError) as exc_info:
        adapter.validate_python(data_file)
    assert exc_info.value.errors()[0]["type"] == "path_exists"

    with pytest.raises(ValidationError) as exc_info:
        adapter.validate_python(tmp_path / "missing" / "new.nc")
    assert exc_info.value.errors()[0]["type"] == "parent_does_not_exist"


@pytest.mark.parametrize("path_type", ["file", "dir", "new"])
@pytest.mark.parametrize("mode", ["python", "json"])
def test_typed_path_expands_home_before_filesystem_checks(
    tmp_path, monkeypatch, path_type, mode
):
    """Validate the expanded home path rather than a literal tilde directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "entry"
    if path_type == "file":
        target.touch()
    elif path_type == "dir":
        target.mkdir()
    adapter = TypeAdapter(path_field(path_type=path_type))
    if mode == "python":
        result = adapter.validate_python("~/entry")
    else:
        result = adapter.validate_json('"~/entry"')
    assert result == target
