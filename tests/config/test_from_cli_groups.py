"""CLI paths compose ordered groups without changing file-cache lifetimes."""

from collections import Counter

import pytest

from tollan.config import RuntimeContext
from tollan.config.sources import (
    ConfigSourceFormat,
    EnvFileConfigSource,
    ListConfigSource,
    YamlConfigSource,
)


def test_cli_groups_and_runtime_tier_precedence(tmp_path):
    config = tmp_path / "settings.yaml"
    config.write_text("_env: {value: yaml}\nyaml_only: true\n")
    env = tmp_path / "settings.env"
    env.write_text("value=env\nENV_ONLY=yes\n")
    rc = RuntimeContext.from_cli(
        config_paths=[config], env_paths=[env], cli_args=["--_env.value", "cli"]
    )
    assert [(s.name, s.order) for s in rc.config_sources] == [
        ("default", -1),
        ("config_paths", 0),
        ("env_paths", 1),
        ("cli_overrides", 2),
        ("info", 1000),
        ("override", 1001),
    ]
    rc.update_default_config({"_env": {"value": "default"}, "default_only": True})
    assert rc.config_dict["_env"]["value"] == "cli"
    assert rc.config_dict["yaml_only"] is True
    assert rc.config_dict["_env"]["ENV_ONLY"] == "yes"
    assert rc.config_dict["default_only"] is True
    assert (
        rc.with_config(overrides={"_env": {"value": "runtime"}}).config_dict["_env"][
            "value"
        ]
        == "runtime"
    )
    assert rc.config_dict["_env"]["value"] == "cli"
    assert (
        RuntimeContext.from_cli(config_paths=[config], env_paths=[env]).config_dict[
            "_env"
        ]["value"]
        == "env"
    )


@pytest.mark.parametrize(
    ("keyword", "suffix", "line"),
    [
        ("config_paths", "yaml", "_env: {{value: {}}}\n"),
        ("env_paths", "env", "value={}\n"),
    ],
)
def test_paths_have_local_orders_and_follow_argument_order(
    tmp_path, keyword, suffix, line
):
    directories = [tmp_path / "first.d", tmp_path / "second.d"]
    for directory in directories:
        directory.mkdir()
        (directory / f"00_base.{suffix}").write_text(line.format("base"))
        (directory / f"9999_last.{suffix}").write_text(line.format(directory.stem))
    override = tmp_path / f"override.{suffix}"
    override.write_text(line.format("override"))

    def load(paths):
        return RuntimeContext.from_cli(
            config_paths=paths if keyword == "config_paths" else None,
            env_paths=paths if keyword == "env_paths" else None,
        )

    rc = load([*directories, override])
    assert rc.config_dict["_env"]["value"] == "override"
    assert (
        load([override, *reversed(directories)]).config_dict["_env"]["value"] == "first"
    )
    group = rc.config_sources.get(lambda s: s.name == keyword)
    assert isinstance(group, ListConfigSource)
    assert [s.order for s in group.source] == [0, 1, 2]
    for path_group in group.source.data[:2]:
        assert isinstance(path_group, ListConfigSource)
        assert [s.order for s in path_group.source] == [0, 9999]


def test_more_than_99_env_files(tmp_path):
    directory = tmp_path / "env.d"
    directory.mkdir()
    for i in range(101):
        (directory / f"{i:03}_settings.env").write_text(f"VALUE={i}\n")
    assert (
        RuntimeContext.from_cli(env_paths=[directory]).config_dict["_env"]["VALUE"]
        == "100"
    )


def test_config_paths_apply_list_patches_across_directories_and_files(tmp_path):
    first = tmp_path / "first.d"
    second = tmp_path / "second.d"
    first.mkdir()
    second.mkdir()
    (first / "00_base.yaml").write_text("items: [base]\n")
    (first / "10_append.yaml").write_text("items: {'[]': [first]}\n")
    (second / "00_append.yaml").write_text("items: {'[]': [second]}\n")
    override = tmp_path / "override.yaml"
    override.write_text("items: {'[]': [last]}\n")
    rc = RuntimeContext.from_cli(config_paths=[first, second, override])
    assert rc.config_dict["items"] == ["base", "first", "second", "last"]


def test_cli_path_groups_share_reads_and_preserve_conditional_includes(
    tmp_path, monkeypatch
):
    directory = tmp_path / "config.d"
    directory.mkdir()
    base = directory / "00_base.yaml"
    base.write_text("items: [base]\n")
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text("- source: patch.yaml\n  enable_if: selected\n")
    included = tmp_path / "patch.yaml"
    included.write_text("items: {'[]': [extra]}\n")
    env = tmp_path / "settings.env"
    env.write_text("TOLLAN_GROUP_VALUE=${TOLLAN_GROUP_INPUT}\n")
    monkeypatch.setenv("TOLLAN_GROUP_INPUT", "first")
    monkeypatch.delenv("TOLLAN_GROUP_VALUE", raising=False)
    reads = []
    yaml_read = YamlConfigSource._read
    env_read = EnvFileConfigSource._read

    def read_yaml(self):
        reads.append(self.source)
        return yaml_read(self)

    def read_env(self):
        reads.append(self.source)
        return env_read(self)

    monkeypatch.setattr(YamlConfigSource, "_read", read_yaml)
    monkeypatch.setattr(EnvFileConfigSource, "_read", read_env)
    rc = RuntimeContext.from_cli(config_paths=[directory, recipe], env_paths=[env])
    assert reads == []
    original = rc.config_dict
    assert original["items"] == ["base"]
    assert original["_env"]["TOLLAN_GROUP_VALUE"] == "first"
    assert rc.config_dict is original
    assert reads == [base, recipe, env]
    variant = rc.with_config(validation_context={"selected": True})
    assert variant.config_dict["items"] == ["base", "extra"]
    assert reads == [base, recipe, env, included]
    for group in (1, 2):
        assert variant.config_sources[group] is rc.config_sources[group]
    with rc.set_context({"selected": True}):
        assert rc.config_dict["items"] == ["base", "extra"]
    assert rc.config_dict is original
    assert Counter(reads) == Counter([base, recipe, included, env])
    monkeypatch.setenv("TOLLAN_GROUP_INPUT", "second")
    assert variant.reload()["_env"]["TOLLAN_GROUP_VALUE"] == "second"
    assert Counter(reads) == Counter([base, recipe, included, env] * 2)
    assert rc.config_dict is original
    rc.config_sources.enable_cache(enabled=False)
    for _ in range(2):
        assert variant.with_config().config_dict["items"] == ["base", "extra"]
    assert Counter(reads) == Counter([base, recipe, included, env] * 4)

    # Dotenv values belong to the runtime; this factory does not export them.
    import os

    assert "TOLLAN_GROUP_VALUE" not in os.environ


def test_cli_group_filtering_logs_skipped_sources(tmp_path):
    from tollan.utils.log import logger

    env = tmp_path / "settings.env"
    env.write_text("IGNORED=env\n")
    yaml = tmp_path / "settings.yaml"
    yaml.write_text("ignored: yaml\n")
    messages = []
    sink = logger.add(messages.append, format="{message}", level="DEBUG")
    try:
        rc = RuntimeContext.from_cli(
            config_paths=[env],
            env_paths=[yaml],
            config_formats={ConfigSourceFormat.yaml},
        )
    finally:
        logger.remove(sink)
    assert set(rc.config_dict) == {"runtime_info"}
    assert any("config_paths: skipping envfile" in message for message in messages)
    assert any("env_paths: skipping yaml" in message for message in messages)


def test_mixed_config_paths_and_yaml_env_overrides(tmp_path):
    directory = tmp_path / "config.d"
    directory.mkdir()
    (directory / "00_base.yaml").write_text(
        "workers: 4\n_env: {HOST: localhost, PORT: '8000'}\n"
    )
    (directory / "10_site.env").write_text("HOST=example.com\n")
    override = tmp_path / "override.yaml"
    override.write_text("_env: {PORT: '9000'}\n")
    rc = RuntimeContext.from_cli(config_paths=[directory, override])
    assert rc.config_dict["workers"] == 4
    assert rc.config_dict["_env"] == {"HOST": "example.com", "PORT": "9000"}
    strict = RuntimeContext.from_cli(
        config_paths=[directory, override], config_formats={ConfigSourceFormat.yaml}
    )
    assert strict.config_dict["_env"] == {"HOST": "localhost", "PORT": "9000"}


@pytest.mark.parametrize("namespace", ["_env", "custom", None])
def test_explicit_env_includes_in_yaml_only_mode(tmp_path, namespace):
    (tmp_path / "settings.env").write_text("VALUE=text\n")
    recipe = tmp_path / "sources.yaml"
    recipe.write_text(
        "- source: settings.env\n  namespace: "
        + ("null" if namespace is None else namespace)
        + "\n"
    )
    config = RuntimeContext.from_cli(
        config_paths=[recipe], config_formats={ConfigSourceFormat.yaml}
    ).config_dict
    values = config if namespace is None else config[namespace]
    assert values["VALUE"] == "text"


@pytest.mark.parametrize("keyword", ["config_paths", "env_paths"])
def test_bare_dotenv_path(tmp_path, keyword):
    path = tmp_path / ".env"
    path.write_text("VALUE=text\n")
    rc = RuntimeContext.from_cli(
        config_paths=[path] if keyword == "config_paths" else None,
        env_paths=[path] if keyword == "env_paths" else None,
    )
    assert rc.config_dict["_env"] == {"VALUE": "text"}


@pytest.mark.parametrize(
    ("formats", "keys"),
    [
        (None, {"setting", "_env"}),
        (set(), set()),
        ({ConfigSourceFormat.yaml}, {"setting"}),
        ({ConfigSourceFormat.envfile}, {"_env"}),
        ({ConfigSourceFormat.yaml, ConfigSourceFormat.envfile}, {"setting", "_env"}),
    ],
)
def test_config_format_selection(tmp_path, formats, keys):
    (tmp_path / "00_settings.yaml").write_text("setting: true\n")
    (tmp_path / "10_settings.env").write_text("VALUE=text\n")
    rc = RuntimeContext.from_cli(config_paths=[tmp_path], config_formats=formats)
    assert set(rc.config_dict) - {"runtime_info"} == keys


@pytest.mark.parametrize("namespace", ["_env", "process", None])
def test_cli_namespace_applies_to_paths_and_nested_includes(tmp_path, namespace):
    (tmp_path / "direct.env").write_text("DIRECT=text\n")
    (tmp_path / "later.env").write_text("LATER=text\n")
    (tmp_path / "included.env").write_text("INCLUDED=text\n")
    (tmp_path / "custom.env").write_text("CUSTOM=text\n")
    (tmp_path / "root.env").write_text("ROOT=text\n")
    (tmp_path / "nested.yaml").write_text(
        "- source:\n    - source: included.env\n"
        "- source: custom.env\n  namespace: custom\n"
        "- source: root.env\n  namespace: null\n"
    )
    rc = RuntimeContext.from_cli(
        config_paths=[tmp_path / "direct.env", tmp_path / "nested.yaml"],
        env_paths=[tmp_path / "later.env"],
        env_namespace=namespace,
    )
    data = rc.config_dict
    values = data if namespace is None else data[namespace]
    assert values["DIRECT"] == values["LATER"] == values["INCLUDED"] == "text"
    assert data["custom"] == {"CUSTOM": "text"}
    assert data["ROOT"] == "text"
    if namespace != "_env":
        assert "_env" not in data
