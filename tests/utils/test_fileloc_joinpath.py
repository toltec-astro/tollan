"""Literal item paths compose with resolved local and remote locations."""

from pathlib import Path, PurePosixPath
from shutil import copytree

import pytest
from pydantic import BaseModel, ConfigDict

from tollan.config.types import SubPath
from tollan.utils.fileloc import fileloc


class Item(BaseModel):
    """An item placed beneath a separately supplied location."""

    model_config = ConfigDict(strict=True)
    path: SubPath


@pytest.mark.spec("file-locations-and-item-paths")
@pytest.mark.parametrize(
    "base",
    ["file:///data/run", "archive:/data/run", "https://example.org/data/run"],
)
def test_join_subpath_retains_location_and_literal_filename(base):
    item = Item.model_validate({"path": "step%3Afit/café #1?.txt"})
    root = fileloc(base)
    original = root.url
    result = root.joinpath(item.path)
    assert result.path == Path("/data/run/step%3Afit/café #1?.txt")
    assert result.url == original + "/step%253Afit/caf%C3%A9%20%231%3F.txt"
    assert result.scheme == root.scheme
    assert result.host == root.host
    assert result.is_local() == root.is_local()
    assert root.url == original


@pytest.mark.spec("file-locations-and-item-paths")
def test_join_preserves_encoded_base_and_other_url_components():
    root = fileloc("https://user:pass@example.org:8443//data%2Fone?q=a%26b#c%23d")
    result = root.joinpath("step:fit", PurePosixPath("result%23.nc"))
    assert result.url == (
        "https://user:pass@example.org:8443//data%2Fone/step%3Afit/result%2523.nc"
        "?q=a%26b#c%23d"
    )


@pytest.mark.spec("file-locations-and-item-paths")
def test_join_uses_path_semantics_without_changing_the_authority():
    root = fileloc("archive:/data/run/")
    assert root.joinpath("plots", "result.png").url == (
        "file://archive/data/run/plots/result.png"
    )
    assert root.joinpath("/other", "result.png").url == (
        "file://archive/other/result.png"
    )


@pytest.mark.spec("file-locations-and-item-paths")
def test_subpath_document_relocates_with_its_payload(tmp_path):
    original = tmp_path / "original"
    payload = original / "step%3Afit/result#1.txt"
    payload.parent.mkdir(parents=True)
    payload.write_text("measurement")
    item = Item.model_validate(
        {"path": payload.relative_to(original)},
        context={"root_path": tmp_path / "unrelated-config-root"},
    )
    restored = Item.model_validate_json(item.model_dump_json(round_trip=True))
    assert restored.path == item.path == PurePosixPath("step%3Afit/result#1.txt")
    assert fileloc(original).joinpath(item.path).path == payload

    moved = tmp_path / "moved"
    copytree(original, moved)
    result = fileloc(moved).joinpath(restored.path)
    assert result.path == moved / item.path
    assert result.path.read_text() == "measurement"
