"""Tests for independently mutable runtime tiers with shared source reads."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from tollan.config import RuntimeConfig, RuntimeContext
from tollan.config.sources import ConfigSourceList, DictConfigSource, ListConfigSource
from tollan.config.sources.yaml import YamlConfigSource
from tollan.config.types import AbsAnyPath


@pytest.mark.parametrize("kind", ["dictionary", "yaml", "explicit", "nested"])
def test_settings_keys_have_the_same_meaning_across_sources(tmp_path, kind):
    settings: dict[str | int, Any] = {
        "data": [{"source": "not-an-include.yaml"}],
        "name": "observation",
    }
    if kind == "yaml":
        source = tmp_path / "settings.yaml"
        source.write_text(yaml.safe_dump(settings))
    elif kind == "explicit":
        source = ConfigSourceList(data=[DictConfigSource(order=0, source=settings)])
    elif kind == "nested":
        source = [ListConfigSource(order=0, source={"data": [{"source": settings}]})]
    else:
        source = {"data": [{"source": settings}]}
    runtime = RuntimeContext(config_sources=source)
    assert runtime.config_dict["data"] == settings["data"]
    assert runtime.config_dict["name"] == settings["name"]


def test_variant_preserves_tier_precedence_and_runtime_info():
    rc = RuntimeContext(
        config_sources=[
            DictConfigSource(order=7, source={"value": "user", "user_only": True})
        ]
    )
    rc.update_default_config({"value": "default", "default_only": 1})
    rc.update_override_config({"override_only": 2})
    original_config = rc.config
    variant = rc.with_config(
        defaults={"value": "variant default", "default_only": 3},
        overrides={"variant_only": 4},
        validation_context={"observation": 5},
    )
    assert variant.config_dict["value"] == "user"
    assert variant.config_dict["default_only"] == 3
    assert variant.config_dict["override_only"] == 2
    assert variant.config_dict["variant_only"] == 4
    assert variant.config_dict["user_only"] is True
    assert variant.config_sources[1] is rc.config_sources[1]
    assert variant.runtime_info.config_sources is variant.config_sources
    assert rc.runtime_info.config_sources is rc.config_sources
    assert variant.runtime_info.validation_context == {"observation": 5}
    assert rc.runtime_info.validation_context == {}
    assert rc.config is original_config
    for tier in ("default", "override", "info"):
        assert variant._get_tier(tier).source is not rc._get_tier(tier).source


def test_updates_to_either_runtime_preserve_the_other():
    rc = RuntimeContext()
    rc.set_override_config({"items": [{"values": [1]}]})
    variant = rc.with_config()
    original_config = rc.config
    variant.update_override_config({"items": {0: {"values": {"[]": [2]}}}})
    assert variant.config_dict["items"] == [{"values": [1, 2]}]
    assert rc.config is original_config
    assert rc.config_dict["items"] == [{"values": [1]}]
    rc.update_override_config({"items": {0: {"values": {"[]": [3]}}}})
    assert rc.config_dict["items"] == [{"values": [1, 3]}]
    assert variant.config_dict["items"] == [{"values": [1, 2]}]


def test_variant_context_is_independent_and_merges_nested_values():
    rc = RuntimeContext().with_config(
        validation_context={"info": {"items": [{"value": 1}]}, "retained": True}
    )
    variant = rc.with_config(validation_context={"info": {"items": {0: {"value": 2}}}})
    assert variant.runtime_info.validation_context == {
        "info": {"items": [{"value": 2}]},
        "retained": True,
    }
    assert rc.runtime_info.validation_context["info"]["items"] == [{"value": 1}]
    with variant.set_context({"temporary": True}):
        assert variant.runtime_info.validation_context["temporary"] is True
        assert "temporary" not in rc.runtime_info.validation_context
    assert "temporary" not in variant.runtime_info.validation_context


def test_variants_reuse_file_reads_and_reload_is_explicit(tmp_path, monkeypatch):
    path = tmp_path / "source.yaml"
    path.write_text("value: 1\n")
    calls = []
    read = YamlConfigSource._read

    def counted_read(self):
        calls.append(self.source)
        return read(self)

    monkeypatch.setattr(YamlConfigSource, "_read", counted_read)
    rc = RuntimeContext(config_sources=path)
    assert rc.config_dict["value"] == 1
    variant = rc.with_config(overrides={"extra": True})
    assert variant.config_dict["value"] == 1
    assert calls == [path]
    path.write_text("value: 2\n")
    assert rc.with_config().config_dict["value"] == 1
    assert calls == [path]
    assert rc.reload()["value"] == 2
    assert rc.with_config().config_dict["value"] == 2
    assert variant.config_dict["value"] == 1
    assert calls == [path, path]


def test_nested_sources_remerge_per_context_and_reuse_file_reads(tmp_path, monkeypatch):
    path = tmp_path / "base.yaml"
    path.write_text("value: 1\n")
    calls = []
    read = YamlConfigSource._read

    def counted_read(self):
        calls.append(self.source)
        return read(self)

    monkeypatch.setattr(YamlConfigSource, "_read", counted_read)
    nested = ConfigSourceList(
        data=[
            YamlConfigSource(order=0, source=path),
            DictConfigSource(order=1, source={"selected": True}, enable_if="selected"),
        ]
    )
    rc = RuntimeContext(config_sources=[ListConfigSource(order=0, source=nested)])
    assert "selected" not in rc.config_dict
    variant = rc.with_config(validation_context={"selected": True})
    assert variant.config_dict["selected"] is True
    assert (
        rc.with_config(validation_context={"selected": False}).config_dict.get(
            "selected"
        )
        is None
    )
    assert calls == [path]
    assert variant.config_sources[1] is rc.config_sources[1]
    assert rc.reload()["value"] == 1
    assert calls == [path, path]


def test_variant_preserves_disabled_file_cache(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("value: 1\n")
    source = YamlConfigSource(order=0, source=path)
    source.enable_cache(enabled=False)
    rc = RuntimeContext(config_sources=[source])
    assert rc.config_dict["value"] == 1
    path.write_text("value: 2\n")
    assert rc.with_config().config_dict["value"] == 2
    assert rc.config_dict["value"] == 1
    path.write_text("value: 3\n")
    assert rc.with_config().config_dict["value"] == 3


def test_with_config_retains_runtime_subclass_and_validation_context(tmp_path):
    class Config(RuntimeConfig):
        path: AbsAnyPath

    class Runtime(RuntimeContext[Config]):
        pass

    rc = Runtime().with_config(
        overrides={"path": "file.dat"}, validation_context={"rootpath": tmp_path}
    )
    assert type(rc) is Runtime
    assert isinstance(rc.config, Config)
    assert rc.config.path == tmp_path / "file.dat"


def test_opaque_values_are_preserved_by_runtime_variant():
    resource = object()
    rc = RuntimeContext()
    settings: dict[str | int, Any] = {"resource": resource}
    rc.set_override_config(settings)
    variant = rc.with_config()
    assert variant.config_dict["resource"] is resource


def test_source_normalization_only_copies_declaration_keys():
    class Opaque:
        def __deepcopy__(self, memo):
            msg = "source payload must not be deep-copied"
            raise AssertionError(msg)

    resource = Opaque()
    declaration = {"source": {"resource": resource}}
    rc = RuntimeContext(config_sources=[declaration])
    assert declaration == {"source": {"resource": resource}}
    assert rc.config_dict["resource"] is resource
    assert rc.with_config().config_dict["resource"] is resource
