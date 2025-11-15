"""Comprehensive tests for config sources functionality."""

from __future__ import annotations

import pytest

from tollan.config.sources import (
    ConfigSourceList,
    DictConfigSource,
    EnvFileConfigSource,
    YamlConfigSource,
    resolve_config_sources,
)


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

    def test_sources_sorted_by_order(self):
        """Test sources are automatically sorted by order."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"last": True}, "order": 2},
                    {"format": "dict", "source": {"first": True}, "order": 0},
                    {"format": "dict", "source": {"middle": True}, "order": 1},
                ],
            },
        )

        # Verify order
        assert sources[0].order == 0
        assert sources[1].order == 1
        assert sources[2].order == 2

    def test_accepts_list_shorthand(self):
        """Test ConfigSourceList accepts list as shorthand."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"key": "value"}, "order": 0},
                ],
            },
        )
        assert sources.load()["key"] == "value"


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

    def test_enable_cache_all_sources(self):
        """Test enable_cache caches all sources by default."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"key": "value"},
                        "order": 0,
                        "name": "test",
                    },
                ],
            },
        )

        sources.enable_cache()

        # First load - populates cache
        config1 = sources.load()
        assert config1["key"] == "value"

        # Verify cache was populated (uses order as key)
        assert 0 in sources._cache_config.cache

        # Second load - should use cached value
        config2 = sources.load()
        assert config2["key"] == "value"

        # Verify cache still contains the source
        assert 0 in sources._cache_config.cache

    def test_enable_cache_with_excludes(self):
        """Test enable_cache with exclude predicate."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {
                        "format": "dict",
                        "source": {"cached": True},
                        "order": 0,
                        "name": "cached_source",
                    },
                    {
                        "format": "dict",
                        "source": {"not_cached": True},
                        "order": 1,
                        "name": "excluded_source",
                    },
                ],
            },
        )

        sources.enable_cache(exclude=lambda s: s.name == "excluded_source")

        # Load to populate cache
        sources.load()

        # Check cache contains only cached_source (uses order as key)
        assert 0 in sources._cache_config.cache
        assert 1 not in sources._cache_config.cache

    def test_enable_cache_with_specific_names(self):
        """Test enable_cache caches only specified names using predicate."""
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

        sources.enable_cache(predicate=lambda s: s.name in {"source_a", "source_c"})
        sources.load()

        assert 0 in sources._cache_config.cache
        assert 1 not in sources._cache_config.cache
        assert 2 in sources._cache_config.cache

    def test_invalidate_cache_all(self):
        """Test invalidate_cache clears all caches."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 1}, "order": 0, "name": "a"},
                    {"format": "dict", "source": {"b": 2}, "order": 1, "name": "b"},
                ],
            },
        )

        sources.enable_cache()
        sources.load()

        assert len(sources._cache_config.cache) > 0

        sources.invalidate_cache()
        assert len(sources._cache_config.cache) == 0

    def test_invalidate_cache_specific_names(self):
        """Test invalidate_cache for specific sources using predicate."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 1}, "order": 0, "name": "a"},
                    {"format": "dict", "source": {"b": 2}, "order": 1, "name": "b"},
                ],
            },
        )

        sources.enable_cache()
        sources.load()

        sources.invalidate_cache(predicate=lambda s: s.name == "a")

        assert 0 not in sources._cache_config.cache
        assert 1 in sources._cache_config.cache

    def test_invalidate_cache_specific_orders(self):
        """Test invalidate_cache for specific orders using predicate."""
        sources = ConfigSourceList.model_validate(
            {
                "data": [
                    {"format": "dict", "source": {"a": 1}, "order": 0},
                    {"format": "dict", "source": {"b": 2}, "order": 1},
                ],
            },
        )

        sources.enable_cache()
        sources.load()

        sources.invalidate_cache(predicate=lambda s: s.order == 0)

        assert 0 not in sources._cache_config.cache
        assert 1 in sources._cache_config.cache


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
        assert config["DATABASE_URL"] == "postgresql://localhost/db"
        assert config["DEBUG"] == "true"

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
        assert config["URL"] == "https://example.com/api"

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
        assert config["VAR"] == "${UNDEFINED}"  # Not interpolated

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

    def test_resolve_config_sources_from_dict(self):
        """Test resolve_config_sources creates ConfigSourceList from dict."""
        csl = resolve_config_sources({"key": "value"})
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

    def test_resolve_config_sources_dict_with_invalid_data_key(self):
        """Test resolve_config_sources raises when dict has 'data' key
        but data is not a list."""
        with pytest.raises(TypeError, match="data must be a sequence"):
            resolve_config_sources({"data": "not a list"})

        with pytest.raises(TypeError, match="data must be a sequence"):
            resolve_config_sources({"data": {"nested": "dict"}})

        with pytest.raises(TypeError, match="data must be a sequence"):
            resolve_config_sources({"data": 123})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
