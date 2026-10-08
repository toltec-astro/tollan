"""Nested source groups preserve sequential updates and cached file reads."""

from copy import deepcopy

import pytest

from tollan.config import RuntimeContext
from tollan.config.sources import (
    ConfigSourceList,
    DictConfigSource,
    EnvFileConfigSource,
    ListConfigSource,
    YamlConfigSource,
)
from tollan.utils.log import logger


def _group(order, sources, **kwargs):
    return ListConfigSource(
        order=order, source=ConfigSourceList(data=sources), **kwargs
    )


@pytest.mark.parametrize(
    ("mappings", "expected"),
    [
        (
            [
                {"items": ["base"]},
                {"items": {"[]": ["a"]}},
                {"items": {"[]": ["b"]}},
                {"items": {"[]": ["c"]}},
            ],
            {"items": ["base", "a", "b", "c"]},
        ),
        (
            [
                {"value": {"old": 1}},
                {"other": True},
                {"value": None},
                {"value": {"new": 2}},
            ],
            {"value": {"new": 2}, "other": True},
        ),
        (
            [
                {"items": [{"a": 1}, {"a": 2}]},
                {"items": {0: {"b": 3}}},
                {"items": {"[1:2]": [{"c": 4}]}},
                {"items": {1: {"d": 5}}},
            ],
            {"items": [{"a": 1, "b": 3}, {"c": 4, "d": 5}]},
        ),
    ],
)
def test_grouping_does_not_change_merge_or_mutate_sources(mappings, expected):
    original = deepcopy(mappings)
    # Inner order numbers must not compete with the outer group's order.
    a, b, c, d = [
        DictConfigSource(order=order, source=data)
        for order, data in zip([-10, 2000, -10, 2000], mappings, strict=True)
    ]
    nested = ConfigSourceList(data=[_group(1, [d, c]), _group(0, [b, a])])
    flat = ConfigSourceList(
        data=[
            source.model_copy(update={"order": i})
            for i, source in enumerate([a, b, c, d])
        ]
    )
    for _ in range(2):
        assert nested.load() == flat.load() == expected
    assert [source.source for source in [a, b, c, d]] == original
    assert mappings == original


def test_disabled_group_skips_descendants_and_retains_condition_logging(tmp_path):
    missing = YamlConfigSource(order=0, source=tmp_path / "missing.yaml")
    sources = ConfigSourceList(
        data=[
            _group(0, [missing], enabled=False),
            _group(1, [missing], name="optional", enable_if="selected"),
        ]
    )
    messages = []
    sink = logger.add(messages.append, format="{message}", level="DEBUG")
    try:
        assert sources.load({"selected": False}) == {}
        assert sources.load() == {}
    finally:
        logger.remove(sink)
    assert any("optional" in message and "disabled" in message for message in messages)
    with pytest.raises(FileNotFoundError):
        sources.load({"selected": True})


def test_yaml_includes_patch_preceding_group_and_reuse_reads(tmp_path, monkeypatch):
    base = tmp_path / "base.yaml"
    base.write_text("items: [{values: [0]}]\n")
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text("""
- source: append.yaml
- enable_if: selected
  source:
    - source: {items: {0: {values: {'[]': [2]}}}}
""")
    included = tmp_path / "append.yaml"
    included.write_text("items: {0: {values: {'[]': [1]}}}\n")
    reads = []
    read = YamlConfigSource._read

    def counted_read(self):
        reads.append(self.source)
        return read(self)

    monkeypatch.setattr(YamlConfigSource, "_read", counted_read)
    base_source = YamlConfigSource(order=0, source=base)
    recipe_source = YamlConfigSource(order=0, source=recipe)
    rc = RuntimeContext(
        config_sources=[_group(0, [base_source]), _group(1, [recipe_source])]
    )
    first = rc.config_dict
    assert first["items"] == [{"values": [0, 1]}]
    assert rc.config_dict is first
    variant = rc.with_config(validation_context={"selected": True})
    assert variant.config_dict["items"] == [{"values": [0, 1, 2]}]
    assert variant.config_sources[1] is rc.config_sources[1]
    assert variant.config_sources[2] is rc.config_sources[2]
    with rc.set_context({"selected": True}):
        assert rc.config_dict["items"] == [{"values": [0, 1, 2]}]
    assert rc.config_dict is first
    assert reads == [base, recipe, included]
    assert base_source.load() == {"items": [{"values": [0]}]}

    included.write_text("items: {0: {values: {'[]': [3]}}}\n")
    assert rc.with_config().config_dict["items"] == [{"values": [0, 1]}]
    assert rc.reload()["items"] == [{"values": [0, 3]}]
    assert reads == [base, recipe, included] * 2
    assert variant.config_dict["items"] == [{"values": [0, 1, 2]}]

    rc.config_sources.enable_cache(enabled=False)
    for _ in range(2):
        assert rc.with_config().config_dict["items"] == [{"values": [0, 3]}]
    assert reads == [base, recipe, included] * 4


def test_nested_env_reads_and_interpolation_are_cached(tmp_path, monkeypatch):
    path = tmp_path / "settings.env"
    path.write_text("VALUE=${TOLLAN_NESTED_TEST_VALUE}\n")
    monkeypatch.setenv("TOLLAN_NESTED_TEST_VALUE", "first")
    reads = []
    read = EnvFileConfigSource._read

    def counted_read(self):
        reads.append(self.source)
        return read(self)

    monkeypatch.setattr(EnvFileConfigSource, "_read", counted_read)
    file = EnvFileConfigSource(order=0, source=path)
    rc = RuntimeContext(config_sources=[_group(0, [_group(0, [file])])])
    assert rc.config_dict["_env"]["VALUE"] == "first"
    monkeypatch.setenv("TOLLAN_NESTED_TEST_VALUE", "second")
    assert rc.with_config().config_dict["_env"]["VALUE"] == "first"
    assert reads == [path]
    assert rc.reload()["_env"]["VALUE"] == "second"
    assert reads == [path, path]


def test_runtime_defaults_and_overrides_keep_their_precedence():
    a = DictConfigSource(order=0, source={"items": {"[]": ["a"]}})
    b = DictConfigSource(order=1, source={"items": {"[]": ["b"]}})
    rc = RuntimeContext(config_sources=[_group(0, [a, b])])
    rc.update_default_config({"items": ["default"]})
    rc.update_override_config({"items": {"[]": ["override"]}})
    assert rc.config_dict["items"] == ["default", "a", "b", "override"]
