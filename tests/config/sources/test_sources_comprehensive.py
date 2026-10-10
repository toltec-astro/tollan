"""Comprehensive tests for config sources functionality."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tollan.config.sources import (
    ConfigSourceList,
    DictConfigSource,
    EnvFileConfigSource,
    ListConfigSource,
    YamlConfigSource,
    resolve_config_sources,
)


@pytest.mark.parametrize(
    ("source_cls", "namespace_field"),
    [(EnvFileConfigSource, "namespace"), (YamlConfigSource, "env_namespace")],
)
class TestSourceNamespaceDefaults:
    """Namespace defaults belong to each concrete source model."""

    @pytest.mark.parametrize(
        ("context", "expected"),
        [
            (None, "_env"),
            ({"env_namespace": "custom"}, "custom"),
            ({"env_namespace": None}, None),
        ],
    )
    def test_omitted_namespace(self, source_cls, namespace_field, context, expected):
        data = {"order": 0, "source": "settings"}
        source = source_cls.model_validate(data, context=context)
        assert getattr(source, namespace_field) == expected
        assert data == {"order": 0, "source": "settings"}

    @pytest.mark.parametrize("namespace", ["_env", "explicit", None])
    def test_explicit_namespace(self, source_cls, namespace_field, namespace):
        source = source_cls.model_validate(
            {"order": 0, "source": "settings", namespace_field: namespace},
            context={"env_namespace": "custom"},
        )
        assert getattr(source, namespace_field) == namespace

    def test_invalid_context_default(self, source_cls, namespace_field):
        with pytest.raises(ValidationError) as exc_info:
            source_cls.model_validate(
                {"order": 0, "source": "settings"},
                context={"env_namespace": 123},
            )
        assert exc_info.value.errors()[0]["loc"] == (namespace_field,)

    def test_existing_source_retains_namespace(self, source_cls, namespace_field):
        source = source_cls(order=0, source="settings")
        validated = source_cls.model_validate(
            source, context={"env_namespace": "custom"}
        )
        assert validated is source
        assert getattr(validated, namespace_field) == "_env"


class TestConfigSourceListBasics:
    """Test basic ConfigSourceList functionality."""

    def test_create_empty_list(self):
        """Test creating empty ConfigSourceList."""
        sources = ConfigSourceList.model_validate({"data": []})
        config = sources.load()
        assert config == {}

    def test_create_with_single_source(self):
        """Test creating ConfigSourceList with single source."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"key": "value"}, "order": 0},
                ],
            },
        )
        config = sources.load()
        assert config["key"] == "value"

    def test_create_with_multiple_sources(self):
        """Test creating ConfigSourceList with multiple sources."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 1, "b": 2}, "order": 0},
                    {"format": "dict", "source": {"b": 3, "c": 4}, "order": 1},
                ],
            },
        )
        config = sources.load()
        assert config["a"] == 1
        assert config["b"] == 3  # Higher order overrides
        assert config["c"] == 4

    @pytest.mark.parametrize("orders", [(2, 0, 1), ("10", "2", "1"), (10, "2", 1)])
    def test_sources_sorted_by_order(self, orders):
        """Sort by validated integer orders, not raw input values."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"value": order}, "order": order}
                    for order in orders
                ],
            },
        )

        assert [source.order for source in sources] == sorted(map(int, orders))
        assert sources.load()["value"] == max(orders, key=int)

    @pytest.mark.parametrize("orders", [(1, "01"), ("1", "01")])
    def test_normalized_orders_must_be_unique(self, orders):
        with pytest.raises(ValidationError, match="orders must be unique"):
            ConfigSourceList.model_validate(
                {
                    "data": [
                        {"format": "dict", "source": {}, "order": order}
                        for order in orders
                    ],
                },
            )

    def test_implicit_order_preserves_explicit_values_and_sources(self):
        existing = DictConfigSource(order=7, source={"last": True})
        declarations = [
            {"source": {"first": True}},
            {"source": {"middle": True}, "order": "2"},
            existing,
        ]
        sources = resolve_config_sources(declarations)

        assert [source.order for source in sources] == [0, 2, 7]
        assert declarations[0] == {"source": {"first": True}}
        assert declarations[1] == {"source": {"middle": True}, "order": "2"}
        assert sources[2] is existing

    def test_implicit_order_conflict_with_explicit_order(self):
        with pytest.raises(ValidationError, match="orders must be unique"):
            resolve_config_sources(
                [{"source": {}}, {"source": {}, "order": "0"}],
            )

    @pytest.mark.parametrize(
        ("declaration", "location"),
        [
            (None, ("data", 0)),
            (
                {"format": "dict", "source": {}, "order": []},
                ("data", 0, "dict", "order"),
            ),
            ({"format": "dict", "source": {}}, ("data", 0, "dict", "order")),
        ],
    )
    def test_invalid_source_reports_nested_validation_error(
        self, declaration, location
    ):
        with pytest.raises(ValidationError) as exc_info:
            ConfigSourceList.model_validate({"data": [declaration]})
        assert exc_info.value.errors()[0]["loc"] == location


class TestConfigSourceListConditionalLoading:
    """Test ConfigSourceList enable_if conditional loading."""

    def test_enable_if_with_matching_context(self):
        """Test source loads when enable_if matches context."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"base": True}, "order": 0},
                    {
                        "format": "dict",
                        "source": {"dev": True},
                        "order": 1,
                        "enable_if": "env == 'dev'",
                    },
                ],
            },
        )

        config = sources.load(context={"env": "dev"})
        assert config["base"] is True
        assert config["dev"] is True

    def test_enable_if_with_non_matching_context(self):
        """Test source skipped when enable_if doesn't match."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"base": True}, "order": 0},
                    {
                        "format": "dict",
                        "source": {"dev": True},
                        "order": 1,
                        "enable_if": "env == 'dev'",
                    },
                ],
            },
        )

        config = sources.load(context={"env": "prod"})
        assert config["base"] is True
        assert "dev" not in config

    def test_enable_if_with_no_context(self):
        """Test source skipped when enable_if provided but no context."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"base": True}, "order": 0},
                    {
                        "format": "dict",
                        "source": {"conditional": True},
                        "order": 1,
                        "enable_if": "env == 'dev'",
                    },
                ],
            },
        )

        config = sources.load()
        assert config["base"] is True
        assert "conditional" not in config

    def test_enable_if_complex_expression(self):
        """Test enable_if with complex boolean expression."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"value": 1},
                        "order": 0,
                        "enable_if": "env == 'dev' and tier == 'premium'",
                    },
                ],
            },
        )

        # Matches
        config1 = sources.load(context={"env": "dev", "tier": "premium"})
        assert config1["value"] == 1

        # Doesn't match
        config2 = sources.load(context={"env": "dev", "tier": "basic"})
        assert "value" not in config2


class TestConfigSourceListCaching:
    """Test ConfigSourceList caching functionality."""

    def test_top_level_list_patches_do_not_mutate_sources(self):
        base = DictConfigSource(order=0, source={"values": [1, 2]})
        patch = DictConfigSource(
            order=1,
            enable_if="patched",
            source={"values": {0: 9, "[]": [3]}},
        )
        sources = ConfigSourceList(data=[base, patch])

        original = sources.load(context={"patched": False})
        changed = sources.load(context={"patched": True})
        assert changed == {"values": [9, 2, 3]}
        assert sources.load(context={"patched": True}) == changed
        assert sources.load(context={"patched": False}) == original
        assert original == base.source == {"values": [1, 2]}
        assert base.load() == original
        assert patch.source == {"values": {0: 9, "[]": [3]}}

        changed["values"].append(4)
        assert sources.load(context={"patched": True}) == {"values": [9, 2, 3]}

    def test_nested_list_patches_do_not_mutate_sources(self):
        base = DictConfigSource(order=0, source={"items": [{"values": [1]}]})
        patch = DictConfigSource(
            order=1,
            enable_if="patched",
            source={"items": {0: {"values": {"[]": [2]}}}},
        )
        sources = ConfigSourceList(data=[base, patch])

        original = sources.load(context={"patched": False})
        changed = sources.load(context={"patched": True})
        assert changed == {"items": [{"values": [1, 2]}]}
        assert sources.load(context={"patched": True}) == changed
        assert sources.load(context={"patched": False}) == original
        assert original == base.source == {"items": [{"values": [1]}]}
        assert base.load() == original
        assert patch.source == {"items": {0: {"values": {"[]": [2]}}}}

        changed["items"][0]["values"].append(3)
        assert sources.load(context={"patched": True}) == {
            "items": [{"values": [1, 2]}],
        }

    @pytest.fixture
    def file_sources(self, tmp_path):
        sources = []
        for order, name in enumerate(("a", "b", "c")):
            path = tmp_path / f"{name}.yaml"
            path.write_text(f"{name}: 1\n")
            sources.append(YamlConfigSource(order=order, name=name, source=path))
        return ConfigSourceList(data=sources)

    def test_enable_cache_all_sources(self, file_sources):
        file_sources.enable_cache()
        assert file_sources.load() == {"a": 1, "b": 1, "c": 1}
        for source in file_sources:
            source.source.write_text(f"{source.name}: 2\n")
        assert file_sources.load() == {"a": 1, "b": 1, "c": 1}

    @pytest.mark.parametrize(
        "selection",
        [
            {"exclude": lambda s: s.name == "b"},
            {"predicate": lambda s: s.name in {"a", "c"}},
        ],
    )
    def test_enable_cache_selection(self, file_sources, selection):
        file_sources.enable_cache(**selection)
        assert file_sources.load() == {"a": 1, "b": 1, "c": 1}
        for source in file_sources:
            source.source.write_text(f"{source.name}: 2\n")
        assert file_sources.load() == {"a": 1, "b": 2, "c": 1}

    @pytest.mark.parametrize(
        ("predicate", "expected"),
        [
            (None, {"a": 2, "b": 2, "c": 2}),
            (lambda s: s.name == "a", {"a": 2, "b": 1, "c": 1}),
            (lambda s: s.order == 0, {"a": 2, "b": 1, "c": 1}),
        ],
    )
    def test_invalidate_cache_selection(self, file_sources, predicate, expected):
        assert file_sources.load() == {"a": 1, "b": 1, "c": 1}
        for source in file_sources:
            source.source.write_text(f"{source.name}: 2\n")
        file_sources.invalidate_cache(predicate=predicate)
        assert file_sources.load() == expected


class TestConfigSourceListGet:
    """Test ConfigSourceList.get method."""

    def test_get_by_name(self):
        """Test get source by name using predicate."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"a": 1},
                        "order": 0,
                        "name": "source_a",
                    },
                    {
                        "format": "dict",
                        "source": {"b": 2},
                        "order": 1,
                        "name": "source_b",
                    },
                ],
            },
        )

        source = sources.get(lambda s: s.name == "source_a")
        assert source is not None
        assert source.order == 0

    def test_get_by_order(self):
        """Test get source by order using predicate."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 1}, "order": 0},
                    {"format": "dict", "source": {"b": 2}, "order": 1},
                ],
            },
        )

        source = sources.get(lambda s: s.order == 1)
        assert source is not None
        assert source.load()["b"] == 2

    def test_get_with_complex_predicate(self):
        """Test get with complex predicate combining conditions."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"a": 1},
                        "order": 0,
                        "name": "source_a",
                    },
                    {
                        "format": "dict",
                        "source": {"b": 2},
                        "order": 1,
                        "name": "source_b",
                    },
                    {
                        "format": "dict",
                        "source": {"c": 3},
                        "order": 2,
                        "name": "source_c",
                    },
                ],
            },
        )

        # Complex predicate: name == "source_a" AND order == 0
        source = sources.get(lambda s: s.name == "source_a" and s.order == 0)
        assert source is not None
        assert source.order == 0

        # Get multiple matches with unique=False
        matches = sources.get(lambda s: s.order > 0, unique=False)
        assert len(matches) == 2
        assert matches[0].order == 1
        assert matches[1].order == 2

    def test_get_returns_none_if_not_found(self):
        """Test get returns None if source not found with predicate."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"a": 1},
                        "order": 0,
                        "name": "source_a",
                    },
                ],
            },
        )

        assert sources.get(lambda s: s.name == "nonexistent") is None
        assert sources.get(lambda s: s.order == 999) is None


class TestDictConfigSource:
    """Test DictConfigSource."""

    def test_dict_source_basic(self):
        """Test DictConfigSource loads dict."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"key": "value"}, "order": 0},
                ],
            },
        )
        source = sources[0]

        assert isinstance(source, DictConfigSource)
        assert source.load()["key"] == "value"

    def test_dict_source_with_integer_keys(self):
        """Test DictConfigSource supports integer keys for list updates."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {0: "first", 1: "second"}, "order": 0},
                ],
            },
        )
        source = sources[0]

        data = source.load()
        assert data[0] == "first"
        assert data[1] == "second"

    def test_dict_source_disabled_raises(self):
        """Test DictConfigSource raises if not enabled."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"key": "value"},
                        "order": 0,
                        "enable_if": "env == 'dev'",
                    },
                ],
            },
        )
        source = sources[0]

        with pytest.raises(ValueError, match="not enabled"):
            source.load(context={"env": "prod"})


class TestEnvFileConfigSource:
    """Test EnvFileConfigSource."""

    def test_envfile_source_basic(self, tmp_path):
        """Test EnvFileConfigSource loads .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_URL=postgresql://localhost/db\nDEBUG=true\n")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "envfile", "source": str(env_file), "order": 0},
                ],
            },
        )
        source = sources[0]

        assert isinstance(source, EnvFileConfigSource)
        config = source.load()
        assert config["_env"]["DATABASE_URL"] == "postgresql://localhost/db"
        assert config["_env"]["DEBUG"] == "true"

    def test_envfile_source_interpolation(self, tmp_path):
        """Test EnvFileConfigSource variable interpolation."""
        env_file = tmp_path / ".env"
        env_file.write_text("DOMAIN=example.com\nURL=https://${DOMAIN}/api\n")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "envfile",
                        "source": str(env_file),
                        "order": 0,
                        "interpolate": True,
                    },
                ],
            },
        )
        source = sources[0]

        config = source.load()
        assert config["_env"]["URL"] == "https://example.com/api"

    def test_envfile_source_no_interpolation(self, tmp_path):
        """Test EnvFileConfigSource without interpolation."""
        env_file = tmp_path / ".env"
        env_file.write_text("VAR=${UNDEFINED}\n")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "envfile",
                        "source": str(env_file),
                        "order": 0,
                        "interpolate": False,
                    },
                ],
            },
        )
        source = sources[0]

        config = source.load()
        assert config["_env"]["VAR"] == "${UNDEFINED}"  # Not interpolated

    def test_envfile_source_auto_names(self, tmp_path):
        """Test EnvFileConfigSource auto-infers name from filename."""
        env_file = tmp_path / "my_config.env"
        env_file.write_text("KEY=value\n")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "envfile", "source": str(env_file), "order": 0},
                ],
            },
        )
        source = sources[0]

        assert source.name == "my_config.env"


class TestResolveConfigSourcesEnvFiles:
    """Test resolve_config_sources with env file paths and directories."""

    def test_single_env_file(self, tmp_path):
        """Single .env file path resolves to EnvFileConfigSource."""
        f = tmp_path / "config.env"
        f.write_text("A=1\n")
        csl = resolve_config_sources(f)
        assert len(csl.data) == 1
        assert isinstance(csl.data[0], EnvFileConfigSource)
        assert csl.data[0].source == f
        assert csl.load() == {"_env": {"A": "1"}}

    def test_directory_expands_env_files_in_order(self, tmp_path):
        """Directory with numbered *.env files resolves to sorted env sources."""
        d = tmp_path / "env.d"
        d.mkdir()
        (d / "00_default.env").write_text("A=1\nB=default\n")
        (d / "10_site.env").write_text("B=2\n")
        csl = resolve_config_sources(d)
        env_srcs = [s for s in csl.data if isinstance(s, EnvFileConfigSource)]
        assert len(env_srcs) == 2
        assert env_srcs[0].source == d / "00_default.env"
        assert env_srcs[1].source == d / "10_site.env"
        assert csl.load() == {"_env": {"A": "1", "B": "2"}}

    def test_directory_mixed_yaml_and_env(self, tmp_path):
        """Directory with mixed yaml and env files resolves both formats."""
        d = tmp_path / "env.d"
        d.mkdir()
        (d / "00_base.yaml").write_text("key: val\n")
        (d / "10_extra.env").write_text("EXTRA=1\n")
        csl = resolve_config_sources(d)
        assert any(isinstance(s, YamlConfigSource) for s in csl.data)
        assert any(isinstance(s, EnvFileConfigSource) for s in csl.data)
        assert csl.load() == {"key": "val", "_env": {"EXTRA": "1"}}

    def test_empty_directory(self, tmp_path):
        """Empty directory results in empty ConfigSourceList."""
        d = tmp_path / "empty.d"
        d.mkdir()
        csl = resolve_config_sources(d)
        assert csl.data == []


class TestYamlConfigSource:
    """Test YamlConfigSource."""

    def test_yaml_source_basic(self, tmp_path):
        """Test YamlConfigSource loads YAML file."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("app: myapp\ndebug: true\nport: 8080\n")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "yaml", "source": str(yaml_file), "order": 0},
                ],
            },
        )
        source = sources[0]

        assert isinstance(source, YamlConfigSource)
        config = source.load()
        assert config["app"] == "myapp"
        assert config["debug"] is True
        assert config["port"] == 8080

    def test_yaml_source_nested_structure(self, tmp_path):
        """Test YamlConfigSource handles nested YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("""
app: myapp
database:
  host: localhost
  port: 5432
  credentials:
    user: admin
    password: secret
""")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "yaml", "source": str(yaml_file), "order": 0},
                ],
            },
        )
        source = sources[0]

        config = source.load()
        assert config["database"]["host"] == "localhost"
        assert config["database"]["credentials"]["user"] == "admin"

    def test_yaml_source_auto_names(self, tmp_path):
        """Test YamlConfigSource auto-infers name from filename."""
        yaml_file = tmp_path / "my_config.yaml"
        yaml_file.write_text("key: value\n")

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "yaml", "source": str(yaml_file), "order": 0},
                ],
            },
        )
        source = sources[0]

        assert source.name == "my_config.yaml"


class TestListConfigSource:
    """Test ListConfigSource for nested source lists."""

    def test_list_source_accepts_settings_dictionary(self):
        source = ListConfigSource(order=0, source={"nested": {"enabled": True}})
        assert source.load() == {"nested": {"enabled": True}}

    def test_list_source_basic(self):
        """Test ListConfigSource loads nested list."""
        nested_sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"nested": True}, "order": 0},
                ],
            },
        )

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"outer": True}, "order": 0},
                    {"format": "list", "source": nested_sources, "order": 1},
                ],
            },
        )

        config = sources.load()
        assert config["outer"] is True
        assert config["nested"] is True

    def test_list_source_merging(self):
        """Test ListConfigSource merges with other sources."""
        nested_sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 1, "b": 2}, "order": 0},
                    {"format": "dict", "source": {"b": 3, "c": 4}, "order": 1},
                ],
            },
        )

        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 0}, "order": 0},
                    {"format": "list", "source": nested_sources, "order": 1},
                ],
            },
        )

        config = sources.load()
        assert config["a"] == 1  # Nested overrides outer
        assert config["b"] == 3  # Nested merges
        assert config["c"] == 4


class TestResolveConfigSourcesFunction:
    """Test resolve_config_sources() wrapper function."""

    @pytest.mark.parametrize(
        "validate", [ConfigSourceList.model_validate, resolve_config_sources]
    )
    @pytest.mark.parametrize(
        "settings",
        [
            {},
            {"search": {"pattern": "warning"}},
            {"name": "application"},
            {"format": "dict", "source": {"value": 7}, "order": 5},
        ],
    )
    def test_settings_dictionary_becomes_one_source(self, validate, settings):
        sources = validate(settings)
        assert len(sources.data) == 1
        assert isinstance(sources[0], DictConfigSource)
        assert sources[0].order == 0
        assert sources.load() == settings
        assert sources.name is None

    def test_resolve_config_sources_from_dict(self):
        """Test resolve_config_sources creates ConfigSourceList from dict."""
        csl = resolve_config_sources(
            {"data": [{"source": {"key": "value"}}], "name": "site"}
        )
        assert isinstance(csl, ConfigSourceList)
        config = csl.load()
        assert config["key"] == "value"

    def test_resolve_config_sources_from_list(self):
        """Test resolve_config_sources creates ConfigSourceList from list."""
        csl = resolve_config_sources(
            [
                {"format": "dict", "source": {"a": 1}, "order": 0},
                {"format": "dict", "source": {"b": 2}, "order": 1},
            ],
        )
        assert isinstance(csl, ConfigSourceList)
        config = csl.load()
        assert config["a"] == 1
        assert config["b"] == 2

    def test_resolve_config_sources_with_order_max(self):
        """Test resolve_config_sources validates order_max constraint."""
        with pytest.raises(ValueError, match="exceeds maximum allowed order"):
            resolve_config_sources(
                [{"format": "dict", "source": {"x": 1}, "order": 10}],
                order_max=5,
            )

    def test_resolve_config_sources_with_order_min(self):
        """Test resolve_config_sources validates order_min constraint."""
        with pytest.raises(ValueError, match="below minimum allowed order"):
            resolve_config_sources(
                [{"format": "dict", "source": {"x": 1}, "order": 0}],
                order_min=5,
            )

    def test_resolve_config_sources_order_constraints_pass(self):
        """Test resolve_config_sources passes validation when constraints are met."""
        csl = resolve_config_sources(
            [{"format": "dict", "source": {"x": 1}, "order": 5}],
            order_min=0,
            order_max=10,
        )
        assert isinstance(csl, ConfigSourceList)
        assert csl.data[0].order == 5

    @pytest.mark.parametrize(
        "form", ["declarations", "nested_list", "list_source", "collection"]
    )
    def test_order_bounds_apply_only_to_immediate_sources(self, form):
        nested = [
            {"order": 2000, "source": {"value": "child_last", "nested": True}},
            {"order": -10, "source": {"value": "child_first"}},
        ]
        if form != "declarations":
            nested = resolve_config_sources(nested)
        group = {"format": "list", "order": 10, "source": nested}
        if form in {"list_source", "collection"}:
            group = ListConfigSource.model_validate(group)
        declarations = [group, {"order": 20, "source": {"value": "outer_last"}}]
        if form == "collection":
            declarations = resolve_config_sources(declarations)

        sources = resolve_config_sources(declarations, order_min=0, order_max=999)

        assert sources.load() == {"value": "outer_last", "nested": True}
        group = sources[0]
        assert isinstance(group, ListConfigSource)
        assert [source.order for source in group.source] == [-10, 2000]
        with pytest.raises(ValueError, match="below minimum allowed order"):
            resolve_config_sources(group.source, order_min=0)

    @pytest.mark.parametrize(
        "value",
        [
            123,
            "settings",
            {"directory": "/observations"},
            [],
            [{"source": "not-an-include.yaml"}],
        ],
    )
    def test_dictionary_data_key_is_configuration(self, value):
        settings = {"data": value, "name": "application"}
        assert (
            resolve_config_sources({"data": [{"source": settings}]}).load() == settings
        )

    @pytest.mark.parametrize(
        "validate", [ConfigSourceList.model_validate, resolve_config_sources]
    )
    @pytest.mark.parametrize(
        "value",
        [
            {"data": 42},
            {"data": ()},
            {"data": [{"format": "dict", "source": "invalid", "order": 0}]},
            {"data": [], "name": {}},
            {"data": [{"format": "dict", "source": {}, "order": "invalid"}]},
        ],
    )
    def test_invalid_collection_does_not_become_settings(self, validate, value):
        with pytest.raises((ValueError, TypeError)):
            validate(value)

    def test_settings_source_retains_order_validation(self):
        with pytest.raises(ValueError, match="below minimum allowed order"):
            resolve_config_sources({"value": 7}, order_min=1)

    @pytest.mark.parametrize("kind", ["file", "directory", "list", "none"])
    def test_model_normalizes_shorthand(self, tmp_path, kind):
        path = tmp_path / "00_base.yaml"
        path.write_text("value: 7\n")
        arg = {
            "file": path,
            "directory": tmp_path,
            "list": [{"source": {"value": 7}}],
            "none": None,
        }[kind]
        sources = ConfigSourceList.model_validate(
            arg, context={"config_source_implicit_order": True}
        )
        assert sources.load() == ({} if kind == "none" else {"value": 7})

    def test_explicit_named_source_list_retains_order_validation(self):
        sources = ConfigSourceList(
            name="site", data=[DictConfigSource(order=5, source={"data": 42})]
        )
        assert resolve_config_sources(sources).load() == {"data": 42}
        assert resolve_config_sources(sources).name == "site"
        with pytest.raises(ValueError, match="exceeds maximum allowed order"):
            resolve_config_sources(sources, order_max=4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
