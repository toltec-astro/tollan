"""File reads are cached independently of conditions and source-list merging."""

import pytest

from tollan.config.sources import (
    ConfigSourceList,
    DictConfigSource,
    EnvFileConfigSource,
    ListConfigSource,
    YamlConfigSource,
)


@pytest.mark.spec("configuration-sources-and-precedence")
def test_file_cache_checks_conditions_on_every_load(tmp_path):
    path = tmp_path / "config.yaml"
    source = YamlConfigSource(order=0, source=path, enable_if="selected")
    with pytest.raises(ValueError, match="not enabled"):
        source.load({"selected": False})
    path.write_text("value: 1\n")
    assert source.load({"selected": True}) == {"value": 1}
    path.write_text("value: 2\n")
    with pytest.raises(ValueError, match="not enabled"):
        source.load({"selected": False})
    assert source.load({"selected": True}) == {"value": 1}
    source.invalidate_cache()
    assert source.load({"selected": True}) == {"value": 2}


def test_empty_file_result_is_cached_but_failed_reads_are_not(tmp_path):
    path = tmp_path / "config.yaml"
    source = YamlConfigSource(order=0, source=path)
    with pytest.raises(FileNotFoundError):
        source.load()
    path.write_text("{}\n")
    assert source.load() == {}
    path.write_text("value: 1\n")
    assert source.load() == {}
    source.invalidate_cache()
    assert source.load() == {"value": 1}


@pytest.mark.spec("configuration-sources-and-precedence")
@pytest.mark.parametrize("namespace", ["_env", "custom", None])
def test_env_interpolation_is_refreshed_with_file_read(
    tmp_path, monkeypatch, namespace
):
    path = tmp_path / ".env"
    path.write_text("SETTING=${TOLLAN_TEST_INPUT}\n")
    source = EnvFileConfigSource(order=0, source=path, namespace=namespace)

    def expected(value):
        values = {"SETTING": value}
        return values if namespace is None else {namespace: values}

    monkeypatch.setenv("TOLLAN_TEST_INPUT", "first")
    assert source.load() == expected("first")
    monkeypatch.setenv("TOLLAN_TEST_INPUT", "second")
    assert source.load() == expected("first")
    source.invalidate_cache()
    assert source.load() == expected("second")


def test_dictionary_source_has_no_read_cache():
    source = DictConfigSource(order=0, source={"value": 1})
    sources = ConfigSourceList(data=[source])
    assert sources.load() == {"value": 1}
    source.source["value"] = 2
    assert sources.load() == {"value": 2}
    sources.invalidate_cache()
    assert source.load() is source.source


@pytest.mark.spec("configuration-sources-and-precedence")
def test_nested_list_invalidation_refreshes_shared_sources(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("value: 1\n")
    file = YamlConfigSource(order=0, source=path)
    nested = ConfigSourceList(data=[file])
    group = ListConfigSource(order=0, source=nested)
    sources = ConfigSourceList(data=[group])
    other = ConfigSourceList(data=[file])
    assert sources.load() == {"value": 1}
    path.write_text("value: 2\n")
    assert other.load() == {"value": 1}
    sources.invalidate_cache()
    assert other.load() == {"value": 2}
    assert sources.load() == {"value": 2}


@pytest.mark.spec("configuration-sources-and-precedence")
def test_list_patch_does_not_modify_cached_file_data(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("items: [{values: [1]}]\n")
    file = YamlConfigSource(order=0, source=path)
    patch = DictConfigSource(
        order=1,
        enable_if="patched",
        source={"items": {0: {"values": {"[]": [2]}}}},
    )
    sources = ConfigSourceList(data=[file, patch])
    assert sources.load({"patched": True}) == {"items": [{"values": [1, 2]}]}
    assert sources.load({"patched": False}) == {"items": [{"values": [1]}]}
    assert sources.load({"patched": True}) == {"items": [{"values": [1, 2]}]}
    assert file.load() == {"items": [{"values": [1]}]}
