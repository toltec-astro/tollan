"""Configuration-specific file-location context."""

from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter

from tollan.config.types import FileLocField
from tollan.utils.fileloc import FileLoc


class Locations(BaseModel):
    configured: list[FileLocField]
    plain: FileLoc


@pytest.mark.parametrize("value", ["data.nc", Path("data.nc"), {"path": "data.nc"}])
def test_root_context_is_opt_in_and_not_mutated(tmp_path, value):
    context = {"rootpath": tmp_path, "other_setting": "retained"}
    model = Locations.model_validate(
        {"configured": [value], "plain": "data.nc"}, context=context
    )
    assert model.configured[0].path == tmp_path / "data.nc"
    assert model.plain.root.local_parent_path is None
    assert context == {"rootpath": tmp_path, "other_setting": "retained"}


@pytest.mark.parametrize("parent", [None, Path("explicit")])
def test_explicit_parent_is_not_replaced_by_root_context(tmp_path, parent):
    adapter = TypeAdapter(FileLocField)
    location = adapter.validate_python(
        {"path": "data.nc", "local_parent_path": parent},
        context={"rootpath": tmp_path},
    )
    assert location.root.local_parent_path == parent
    location = adapter.validate_python(
        "data.nc", context={"rootpath": tmp_path, "local_parent_path": parent}
    )
    assert location.root.local_parent_path == parent


def test_other_fileloc_context_reaches_validation(tmp_path):
    context = {"rootpath": tmp_path, "remote_parent_path": Path("/archive")}
    location = TypeAdapter(FileLocField).validate_python(
        "host:data.nc", context=context
    )
    assert location.root.local_parent_path == tmp_path
    assert location.root.remote_parent_path == Path("/archive")
    assert location.path == Path("/archive/data.nc")
    assert "local_parent_path" not in context


def test_prevalidated_location_keeps_its_context(tmp_path):
    location = FileLoc.model_validate("data.nc")
    result = TypeAdapter(FileLocField).validate_python(
        location, context={"rootpath": tmp_path}
    )
    assert result is location
    assert result.root.local_parent_path is None


def test_no_root_uses_native_fileloc_validation():
    location = TypeAdapter(FileLocField).validate_python("data.nc")
    assert location.root.local_parent_path is None
    assert location.root.path == Path("data.nc")


def test_nested_json_roundtrip_keeps_parent_settings(tmp_path):
    model = Locations.model_validate(
        {"configured": ["data.nc"], "plain": "other.nc"},
        context={"rootpath": tmp_path},
    )
    restored = Locations.model_validate_json(
        model.model_dump_json(round_trip=True),
        context={"rootpath": tmp_path / "different"},
    )
    assert restored.configured[0].path == tmp_path / "data.nc"
    assert restored.plain.root.local_parent_path is None
