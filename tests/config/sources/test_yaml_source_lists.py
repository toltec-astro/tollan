"""YAML source lists reuse parsing while resolving current-context settings."""

import pytest
import yaml

from tollan.config import RuntimeContext
from tollan.config.sources import YamlConfigSource


def test_yaml_list_conditions_remerge_without_mutating_cached_sources(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("""
- source: {items: [{values: [1]}]}
- enable_if: workers >= 4
  source: {items: {0: {values: {'[]': [2]}}}}
""")
    source = YamlConfigSource(order=0, source=path)
    assert source.load({"workers": 8}) == {"items": [{"values": [1, 2]}]}
    assert source.load({"workers": 2}) == {"items": [{"values": [1]}]}
    assert source.load({"workers": 8}) == {"items": [{"values": [1, 2]}]}


def test_nested_lists_have_local_explicit_and_implicit_orders(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("""
- source:
    - order: 2000
      source: {value: last}
    - order: -10
      source: {value: first}
- source:
    - source: {extra: first}
    - source: {extra: last}
""")
    rc = RuntimeContext(config_sources=path)
    assert rc.config_dict["value"] == "last"
    assert rc.config_dict["extra"] == "last"


def test_relative_includes_nested_lists_and_envfiles(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    directory.mkdir()
    included = directory / "included"
    included.mkdir()
    (included / "settings.yaml").write_text("path: relative.dat\nvalue: included\n")
    (included / "sources.yaml").write_text("- source: settings.yaml\n")
    (directory / "settings.env").write_text("SETTING=from_env\n")
    root = directory / "config.yaml"
    root.write_text("""
- source:
    - source: included/sources.yaml
- format: list
  source:
    data:
      - source: settings.env
""")
    # Includes are relative to each containing file, not the working directory.
    monkeypatch.chdir(tmp_path)
    assert YamlConfigSource(order=0, source=root).load() == {
        "path": "relative.dat",
        "value": "included",
        "SETTING": "from_env",
    }


def test_disabled_include_does_not_open_missing_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- source: missing.yaml\n  enable_if: workers >= 4\n")
    source = YamlConfigSource(order=0, source=path)
    assert source.load({"workers": 2}) == {}
    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        source.load({"workers": 8})


def test_variants_share_recipe_and_include_reads_until_reload(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    included = tmp_path / "included.yaml"
    path.write_text("""
- source: included.yaml
- enable_if: workers >= 4
  source: {selected: true}
""")
    included.write_text("value: 1\n")
    reads = []
    read = YamlConfigSource._read

    def counted_read(self):
        reads.append(self.source)
        return read(self)

    monkeypatch.setattr(YamlConfigSource, "_read", counted_read)
    rc = RuntimeContext(config_sources=path)
    assert rc.config_dict["value"] == 1
    variant = rc.with_config(validation_context={"workers": 8})
    assert variant.config_dict["selected"] is True
    assert reads == [path, included]
    included.write_text("value: 2\n")
    assert rc.with_config().config_dict["value"] == 1
    assert reads == [path, included]
    assert rc.reload()["value"] == 2
    assert reads == [path, included, path, included]
    assert variant.config_dict["value"] == 1


def test_disabling_recipe_cache_rereads_includes(tmp_path):
    path = tmp_path / "config.yaml"
    included = tmp_path / "included.yaml"
    path.write_text("- source: included.yaml\n")
    included.write_text("value: 1\n")
    source = YamlConfigSource(order=0, source=path)
    assert source.load() == {"value": 1}
    source.enable_cache(enabled=False)
    included.write_text("value: 2\n")
    assert source.load() == {"value": 2}


def test_numbered_directory_combines_mappings_and_conditional_lists(tmp_path):
    (tmp_path / "00_base.yaml").write_text("value: base\nretained: true\n")
    (tmp_path / "10_overrides.yaml").write_text("""
- source: {value: override}
  enable_if: workers >= 4
""")
    rc = RuntimeContext(config_sources=tmp_path)
    assert rc.config_dict["value"] == "base"
    selected = rc.with_config(
        defaults={"value": "default"},
        validation_context={"workers": 8},
    )
    assert selected.config_dict["value"] == "override"
    assert selected.config_dict["retained"] is True
    assert (
        selected.with_config(overrides={"value": "cli"}).config_dict["value"] == "cli"
    )


@pytest.mark.parametrize("document", ["", "# comment only\n", "null", "{}", "[]"])
def test_empty_yaml_configurations(tmp_path, document):
    path = tmp_path / "config.yaml"
    path.write_text(document)
    assert YamlConfigSource(order=0, source=path).load() == {}


@pytest.mark.parametrize("document", ["42", "false", "text", "[1, 2]", "- source: [1]"])
def test_invalid_document_does_not_silently_disappear(tmp_path, document):
    path = tmp_path / "config.yaml"
    path.write_text(document)
    with pytest.raises(ValueError, match="mapping"):
        YamlConfigSource(order=0, source=path).load()


def test_invalid_source_declaration_reports_validation_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- format: dict\n")
    with pytest.raises(ValueError, match="source"):
        YamlConfigSource(order=0, source=path).load()


def test_duplicate_local_orders_are_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- {source: {}, order: 0}\n- {source: {}, order: 0}\n")
    with pytest.raises(ValueError, match="orders must be unique"):
        YamlConfigSource(order=0, source=path).load()


def test_mapping_with_source_like_keys_remains_ordinary_config(tmp_path):
    data = {"data": [{"source": "not-an-include.yaml"}], "source": "relative.dat"}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    assert YamlConfigSource(order=0, source=path).load() == data
