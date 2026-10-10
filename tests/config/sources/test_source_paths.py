"""Source references resolve through typed validation, independently of settings."""

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from tollan.config.sources import (
    ConfigSourceList,
    EnvFileConfigSource,
    ListConfigSource,
    YamlConfigSource,
    resolve_config_sources,
)
from tollan.config.types import AnyPath, FileLocField


@pytest.mark.parametrize("source_cls", [YamlConfigSource, EnvFileConfigSource])
def test_file_source_field_uses_context_without_opening(tmp_path, source_cls):
    source = source_cls.model_validate(
        {"order": 0, "source": "missing.file"},
        context={
            "config_source_root_path": tmp_path,
            "root_path": tmp_path / "application",
        },
    )
    assert source.source == tmp_path / "missing.file"


@pytest.mark.parametrize("source_cls", [YamlConfigSource, EnvFileConfigSource])
def test_file_source_does_not_use_application_root(tmp_path, source_cls):
    source = source_cls.model_validate(
        {"order": 0, "source": "settings.yaml"},
        context={"root_path": tmp_path},
    )
    assert source.source == Path("settings.yaml")


def test_source_loading_and_setting_paths_have_independent_roots(tmp_path):
    source_root = tmp_path / "configuration"
    source_root.mkdir()
    (source_root / "settings.yaml").write_text("path: observation.nc\n")
    context = {
        "config_source_root_path": source_root,
        "root_path": tmp_path / "data",
        "config_source_implicit_order": True,
    }
    sources = ConfigSourceList.model_validate("settings.yaml", context=context)
    settings = sources.load()
    assert settings == {"path": "observation.nc"}
    assert TypeAdapter(AnyPath).validate_python(settings["path"], context=context) == (
        tmp_path / "data" / "observation.nc"
    )
    location = TypeAdapter(FileLocField).validate_python(
        settings["path"], context=context
    )
    assert location.path == tmp_path / "data" / "observation.nc"
    source_context = {"config_source_root_path": source_root}
    assert TypeAdapter(AnyPath).validate_python(
        "data.nc", context=source_context
    ) == Path("data.nc")


def test_nested_lists_keep_path_and_namespace_context(tmp_path):
    declarations = [
        {
            "source": [
                {"source": "settings.yaml"},
                {"format": "list", "source": {"data": [{"source": "settings.env"}]}},
            ]
        },
        {"source": {"source": "literal.yaml", "path": "relative.dat"}},
    ]
    original = deepcopy(declarations)
    context = {
        "config_source_root_path": tmp_path,
        "root_path": tmp_path / "application",
        "env_namespace": "process",
        "config_source_implicit_order": True,
    }
    original_context = context.copy()
    sources = ConfigSourceList.model_validate(declarations, context=context)

    group = sources[0]
    assert isinstance(group, ListConfigSource)
    file, subgroup = group.source
    assert isinstance(file, YamlConfigSource)
    assert isinstance(subgroup, ListConfigSource)
    envfile = subgroup.source[0]
    assert isinstance(envfile, EnvFileConfigSource)
    assert file.source == tmp_path / "settings.yaml"
    assert file.env_namespace == "process"
    assert envfile.source == tmp_path / "settings.env"
    assert envfile.namespace == "process"
    assert sources[1].source == original[1]["source"]
    assert declarations == original
    assert context == original_context


@pytest.mark.parametrize("relative_root", [False, True])
@pytest.mark.parametrize("form", ["file", "directory", "nested_directory"])
def test_resolver_roots_path_shorthand(tmp_path, monkeypatch, relative_root, form):
    directory = tmp_path / "config"
    directory.mkdir()
    group = directory / "group"
    group.mkdir()
    (group / "00_settings.yaml").write_text("value: 1\n")
    monkeypatch.chdir(tmp_path)
    config_source_root_path = Path("config") if relative_root else directory
    arg = {
        "file": "group/00_settings.yaml",
        "directory": "group",
        "nested_directory": [{"format": "list", "source": "group"}],
    }[form]

    sources = resolve_config_sources(
        arg, config_source_root_path=config_source_root_path
    )

    assert sources.load() == {"value": 1}


def test_reused_sources_keep_paths_and_cached_reads(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("value: 1\n")
    file = YamlConfigSource(order=0, source=path)
    group = ListConfigSource(order=0, source=[file])
    assert group.load() == {"value": 1}
    path.write_text("value: 2\n")

    sources = resolve_config_sources(
        [group], config_source_root_path=tmp_path / "elsewhere"
    )

    assert sources[0] is group
    assert sources[0].source[0] is file
    assert sources.load() == {"value": 1}


def test_invalid_nested_source_path_has_field_location(tmp_path):
    with pytest.raises(ValidationError) as exc_info:
        resolve_config_sources(
            [{"source": [{"format": "yaml", "source": 123}]}],
            config_source_root_path=tmp_path,
        )
    assert exc_info.value.errors()[0]["loc"] == (
        "data",
        0,
        "list",
        "source",
        "data",
        0,
        "yaml",
        "source",
    )
