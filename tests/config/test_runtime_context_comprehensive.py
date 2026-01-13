"""Comprehensive tests for RuntimeContext functionality."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel

from tollan.config import (
    ConfigHandler,
    RuntimeConfig,
    RuntimeContext,
    SubConfigKeyTransformer,
)


class TestRuntimeContextBasics:
    """Test basic RuntimeContext functionality."""

    def test_create_empty_context(self):
        """Test creating RuntimeContext with no config sources."""
        rc = RuntimeContext()
        assert rc.config_dict is not None
        assert isinstance(rc.config, RuntimeConfig)

    def test_create_with_dict_source(self):
        """Test creating RuntimeContext with dict source."""
        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"app": "test", "version": "1.0"},
                    "order": 0,
                },
            ],
        )
        assert rc.config_dict["app"] == "test"
        assert rc.config_dict["version"] == "1.0"

    def test_create_with_multiple_sources(self):
        """Test creating RuntimeContext with multiple sources."""
        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"app": "test", "debug": False},
                    "order": 0,
                },
                {"format": "dict", "source": {"debug": True, "port": 8080}, "order": 1},
            ],
        )
        # Higher order overrides lower order
        assert rc.config_dict["app"] == "test"
        assert rc.config_dict["debug"] is True
        assert rc.config_dict["port"] == 8080

    def test_config_dict_is_cached(self):
        """Test that config_dict is cached property."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
            ],
        )
        config1 = rc.config_dict
        config2 = rc.config_dict
        # Same object (cached)
        assert config1 is config2

    def test_config_is_cached(self):
        """Test that config is cached property."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
            ],
        )
        config1 = rc.config
        config2 = rc.config
        # Same object (cached)
        assert config1 is config2


class TestRuntimeContextCLI:
    """Test RuntimeContext.from_cli factory method."""

    def test_from_cli_with_cli_args_only(self):
        """Test from_cli with only CLI args."""
        rc = RuntimeContext.from_cli(
            cli_args=["--app", "myapp", "--debug", "true", "--server.port", "8080"],
        )
        assert rc.config_dict["app"] == "myapp"
        assert rc.config_dict["debug"] is True
        assert rc.config_dict["server"]["port"] == 8080

    def test_from_cli_with_nested_keys(self):
        """Test from_cli parses nested keys correctly."""
        rc = RuntimeContext.from_cli(
            cli_args=["--db.host", "localhost", "--db.port", "5432"],
        )
        assert rc.config_dict["db"]["host"] == "localhost"
        assert rc.config_dict["db"]["port"] == 5432

    def test_from_cli_empty(self):
        """Test from_cli with no arguments."""
        rc = RuntimeContext.from_cli()
        # Should work, just has empty config
        assert rc.config_dict is not None


class TestRuntimeContextSetContext:
    """Test RuntimeContext.set_context context manager."""

    def test_set_context_temporary_override(self):
        """Test set_context temporarily overrides context."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
                {
                    "format": "dict",
                    "source": {"debug": True},
                    "order": 1,
                    "enable_if": "env == 'dev'",
                },
            ],
        )

        # Without context, enable_if fails
        assert "debug" not in rc.config_dict

        # With context, enable_if succeeds
        with rc.set_context({"env": "dev"}):
            assert rc.config_dict["debug"] is True

        # After context manager, back to original
        assert "debug" not in rc.config_dict

    def test_set_context_restores_cache(self):
        """Test set_context restores cached values after exit."""
        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"app": "test", "version": "1.0"},
                    "order": 0,
                },
            ],
        )

        # Load config to populate cache
        original_config = rc.config_dict
        assert original_config["version"] == "1.0"

        # Context manager should restore cache
        with rc.set_context({"env": "prod"}):
            _context_config = rc.config_dict

        # After exit, cache should be restored
        restored_config = rc.config_dict
        assert restored_config is original_config

    def test_set_context_merges_with_existing(self):
        """Test set_context merges with existing context."""
        rc = RuntimeContext()
        # Set initial context via runtime_info validation_context
        validation_context = rc._get_validation_context()
        validation_context["existing"] = "value"

        with rc.set_context({"new": "value"}):
            validation_context = rc._get_validation_context()
            assert validation_context["existing"] == "value"
            assert validation_context["new"] == "value"

        # After exit, only existing remains
        validation_context = rc._get_validation_context()
        assert validation_context == {"existing": "value"}


class TestRuntimeContextTierManipulation:
    """Test RuntimeContext tier manipulation methods."""

    def test_update_override_config(self):
        """Test update_override_config adds to override tier."""
        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"app": "test", "debug": False},
                    "order": 0,
                },
            ],
        )

        # Update override tier
        rc.update_override_config({"debug": True, "new_key": "value"})

        assert rc.config_dict["debug"] is True  # Overridden
        assert rc.config_dict["new_key"] == "value"
        assert rc.config_dict["app"] == "test"  # Preserved

    def test_set_override_config(self):
        """Test set_override_config replaces override tier."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
            ],
        )

        # Set override tier
        rc.set_override_config({"override": "value1"})
        assert rc.config_dict["override"] == "value1"

        # Replace override tier
        rc.set_override_config({"override": "value2", "new": "value"})
        assert rc.config_dict["override"] == "value2"
        assert rc.config_dict["new"] == "value"

    def test_update_default_config(self):
        """Test update_default_config adds to default tier."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
            ],
        )

        # Update default tier (lowest priority)
        rc.update_default_config({"app": "default_app", "fallback": "value"})

        assert rc.config_dict["app"] == "test"  # Not overridden (higher priority)
        assert rc.config_dict["fallback"] == "value"  # Added

    def test_set_default_config(self):
        """Test set_default_config replaces default tier."""
        rc = RuntimeContext()

        rc.set_default_config({"default1": "value1"})
        assert rc.config_dict["default1"] == "value1"

        rc.set_default_config({"default2": "value2"})
        assert "default1" not in rc.config_dict  # Replaced
        assert rc.config_dict["default2"] == "value2"


class TestRuntimeContextReload:
    """Test RuntimeContext.reload method."""

    def test_reload_invalidates_caches(self):
        """Test reload invalidates all caches."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
            ],
        )

        # Load config to populate cache
        config1 = rc.config_dict

        # Reload should invalidate cache
        config2 = rc.reload()

        # New dict object (cache invalidated)
        assert config2 is not config1
        assert config2 == config1  # But same content

    def test_reload_with_modified_source(self):
        """Test reload invalidates caches and forces fresh load."""
        rc = RuntimeContext(
            config_sources=[
                {"format": "dict", "source": {"app": "test"}, "order": 0},
            ],
        )

        assert rc.config_dict["app"] == "test"

        # Update via runtime context (not underlying source)
        rc.update_override_config({"app": "modified"})

        # Reload should return new config
        reloaded = rc.reload()
        assert reloaded["app"] == "modified"


class TestRuntimeContextGetItem:
    """Test RuntimeContext.__getitem__ for ConfigHandler access."""

    def test_getitem_with_single_handler(self):
        """Test __getitem__ returns ConfigHandler instance."""

        class TestConfig(BaseModel):
            value: str = "test"

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "handler_test"}

        rc = RuntimeContext()
        handler = rc[TestHandler]

        assert isinstance(handler, TestHandler)
        assert handler.config.value == "handler_test"

    def test_getitem_with_multiple_handlers(self):
        """Test __getitem__ with tuple returns tuple of handlers."""

        class TestConfig1(BaseModel):
            value: str = "test1"

        class TestConfig2(BaseModel):
            value: str = "test2"

        class TestHandler1(ConfigHandler[TestConfig1]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "handler1"}

        class TestHandler2(ConfigHandler[TestConfig2]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "handler2"}

        rc = RuntimeContext()
        h1, h2 = rc[TestHandler1, TestHandler2]

        assert isinstance(h1, TestHandler1)
        assert isinstance(h2, TestHandler2)
        assert h1.config.value == "handler1"
        assert h2.config.value == "handler2"

    def test_getitem_with_unregistered_handler_raises(self):
        """Test __getitem__ raises TypeError for unregistered handler."""

        # Create handler that's not registered
        class UnregisteredConfig(BaseModel):
            value: str

        # Manually prevent registration
        class UnregisteredHandler(ConfigHandler[UnregisteredConfig]):
            pass

        # Remove from registry if it got registered
        RuntimeContext.config_handler_cls_registry.discard(UnregisteredHandler)

        rc = RuntimeContext()

        with pytest.raises(TypeError, match="not registered"):
            rc[UnregisteredHandler]


class TestRuntimeContextSubConfigKeyTransformer:
    """Test SubConfigKeyTransformer pattern."""

    def test_subconfig_key_transformer_basic(self):
        """Test SubConfigKeyTransformer extracts subconfig."""

        class DatabaseConfig(BaseModel):
            host: str
            port: int = 5432

        class DatabaseHandler(
            SubConfigKeyTransformer[Literal["database"]],
            ConfigHandler[DatabaseConfig],
        ):
            pass

        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"database": {"host": "localhost", "port": 3306}},
                    "order": 0,
                },
            ],
        )

        handler = DatabaseHandler(rc)
        assert handler.config.host == "localhost"
        assert handler.config.port == 3306

    def test_subconfig_key_transformer_with_updates(self):
        """Test SubConfigKeyTransformer prepare_runtime_config_data."""

        class CacheConfig(BaseModel):
            enabled: bool = True
            ttl: int = 3600

        class CacheHandler(
            SubConfigKeyTransformer[Literal["cache"]],
            ConfigHandler[CacheConfig],
        ):
            pass

        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"cache": {"enabled": False}},
                    "order": 0,
                },
            ],
        )

        handler = CacheHandler(rc)
        assert handler.config.enabled is False

        # Update config
        handler.update_config({"enabled": True, "ttl": 7200})

        # Check that update was applied to runtime config under "cache" key
        assert rc.config_dict["cache"]["enabled"] is True
        assert rc.config_dict["cache"]["ttl"] == 7200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
