"""Comprehensive tests for ConfigHandler functionality."""

from __future__ import annotations

from functools import cached_property

import pytest
from pydantic import BaseModel

from tollan.config import ConfigHandler, RuntimeContext


class TestConfigHandlerBasics:
    """Test basic ConfigHandler functionality."""

    def test_handler_initialization(self):
        """Test ConfigHandler can be initialized with RuntimeContext."""

        class TestConfig(BaseModel):
            value: str = "test"

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

        rc = RuntimeContext()
        handler = TestHandler(rc)

        assert handler.rc is rc
        assert handler.runtime_config is rc.config
        assert handler.runtime_info is rc.runtime_info

    def test_handler_config_property(self):
        """Test ConfigHandler.config property loads and caches."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "cached_value"}

        rc = RuntimeContext()
        handler = TestHandler(rc)

        # First access loads config
        config1 = handler.config
        assert config1.value == "cached_value"

        # Second access returns cached
        config2 = handler.config
        assert config2 is config1

    def test_handler_load_config(self):
        """Test ConfigHandler.load_config validates data."""

        class TestConfig(BaseModel):
            required_field: str
            optional_field: int = 42

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"required_field": "value"}

        rc = RuntimeContext()
        handler = TestHandler(rc)

        config = handler.load_config()
        assert config.required_field == "value"
        assert config.optional_field == 42

    def test_handler_must_implement_prepare_config_data(self):
        """Test ConfigHandler raises if prepare_config_data not implemented."""

        class TestConfig(BaseModel):
            value: str

        class BadHandler(ConfigHandler[TestConfig]):
            pass  # Missing prepare_config_data

        rc = RuntimeContext()
        handler = BadHandler(rc)

        with pytest.raises(NotImplementedError, match="prepare_config_data"):
            handler.load_config()

    def test_handler_must_implement_prepare_runtime_config_data(self):
        """Test ConfigHandler raises if prepare_runtime_config_data not implemented."""

        class TestConfig(BaseModel):
            value: str

        class BadHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

        rc = RuntimeContext()
        handler = BadHandler(rc)

        with pytest.raises(NotImplementedError, match="prepare_runtime_config_data"):
            handler.update_config({"value": "new"})


class TestConfigHandlerUpdates:
    """Test ConfigHandler update functionality."""

    def test_update_config_mode_override(self):
        """Test update_config with override mode."""

        class TestConfig(BaseModel):
            field1: str = "default1"
            field2: str = "default2"

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                # Extract from runtime config extra fields
                extra = getattr(runtime_config, "__pydantic_extra__", {})
                return extra.get("test_config", {})

            @classmethod
            def prepare_runtime_config_data(cls, config_data):  # type: ignore[override]
                return {"test_config": config_data}

        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"test_config": {"field1": "value1", "field2": "value2"}},
                    "order": 0,
                },
            ],
        )

        handler = TestHandler(rc)
        assert handler.config.field1 == "value1"
        assert handler.config.field2 == "value2"

        # Update with override
        handler.update_config({"field1": "new_value"}, tier="override")

        # field1 overridden, field2 preserved
        assert handler.config.field1 == "new_value"
        assert handler.config.field2 == "value2"

    def test_update_config_mode_default(self):
        """Test update_config with default mode."""

        class TestConfig(BaseModel):
            field1: str = "default1"
            field2: str = "default2"

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                extra = getattr(runtime_config, "__pydantic_extra__", {})
                return extra.get("test_config", {})

            @classmethod
            def prepare_runtime_config_data(cls, config_data):  # type: ignore[override]
                return {"test_config": config_data}

        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"test_config": {"field1": "value1"}},
                    "order": 0,
                },
            ],
        )

        handler = TestHandler(rc)

        # Update with default mode (lower priority)
        handler.update_config(
            {"field1": "default_value", "field2": "new_value"},
            tier="default",
        )

        # field1 not overridden (already set), field2 added
        assert handler.config.field1 == "value1"
        assert handler.config.field2 == "new_value"

    def test_update_config_invalid_mode_raises(self):
        """Test update_runtime_config raises with invalid mode."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):  # type: ignore[override]
                return {"test": config_data}

        rc = RuntimeContext()
        handler = TestHandler(rc)

        with pytest.raises(ValueError, match="Invalid update tier"):
            handler.update_runtime_config({"test": {"value": "new"}}, tier="invalid")  # type: ignore[arg-type]

    def test_update_invalidates_cache(self):
        """Test update_config invalidates cached config."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                extra = getattr(runtime_config, "__pydantic_extra__", {})
                return extra.get("test", {})

            @classmethod
            def prepare_runtime_config_data(cls, config_data):  # type: ignore[override]
                return {"test": config_data}

        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"test": {"value": "original"}},
                    "order": 0,
                },
            ],
        )

        handler = TestHandler(rc)

        # Load config
        config1 = handler.config
        assert config1.value == "original"

        # Update config
        handler.update_config({"value": "updated"})

        # Cache should be invalidated
        config2 = handler.config
        assert config2.value == "updated"
        assert config2 is not config1  # New object


class TestConfigHandlerAutoCacheReset:
    """Test ConfigHandler.auto_cache_reset decorator."""

    def test_auto_cache_reset_decorator(self):
        """Test auto_cache_reset marks property for reset."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                extra = getattr(runtime_config, "__pydantic_extra__", {})
                return extra.get("test", {})

            @classmethod
            def prepare_runtime_config_data(cls, config_data):  # type: ignore[override]
                return {"test": config_data}

            @ConfigHandler.auto_cache_reset
            @cached_property
            def expensive_computation(self):
                return f"computed_{self.config.value}"

        rc = RuntimeContext(
            config_sources=[
                {
                    "format": "dict",
                    "source": {"test": {"value": "original"}},
                    "order": 0,
                },
            ],
        )

        handler = TestHandler(rc)

        # First computation
        result1 = handler.expensive_computation
        assert result1 == "computed_original"

        # Update config
        handler.update_config({"value": "updated"})

        # Property should be recomputed
        result2 = handler.expensive_computation
        assert result2 == "computed_updated"

    def test_auto_cache_reset_only_on_cached_property(self):
        """Test auto_cache_reset raises if not used on cached_property."""

        with pytest.raises(
            TypeError,
            match="auto_cache_reset can only be used on cached_property",
        ):

            class TestHandler(ConfigHandler):
                @ConfigHandler.auto_cache_reset  # type: ignore[arg-type]
                def not_cached(self):
                    return "value"

    def test_auto_cache_reset_preserves_property(self):
        """Test auto_cache_reset returns the same cached_property."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

            @ConfigHandler.auto_cache_reset
            @cached_property
            def my_property(self):
                return "value"

        # Verify it's still a cached_property
        assert isinstance(TestHandler.my_property, cached_property)
        assert "my_property" in TestHandler._auto_cache_reset_registry[TestHandler]


class TestConfigHandlerTypeInference:
    """Test ConfigHandler config_model_cls inference."""

    def test_infers_config_model_cls_from_generic(self):
        """Test config_model_cls is inferred from Generic parameter."""

        class MyConfig(BaseModel):
            value: str

        class MyHandler(ConfigHandler[MyConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

        # config_model_cls should be inferred
        assert MyHandler.config_model_cls is MyConfig

    def test_explicit_config_model_cls_disallowed(self):
        """Test explicit config_model_cls is now disallowed (enforcement)."""

        class ConfigA(BaseModel):
            value: str

        class ConfigB(BaseModel):
            value: str

        # Explicit config_model_cls should raise TypeError
        with pytest.raises(TypeError, match="explicitly sets 'config_model_cls'"):

            class MyHandler(ConfigHandler[ConfigA]):
                config_model_cls: type[BaseModel] = ConfigB  # type: ignore[misc,assignment]  # Should be disallowed

                @classmethod
                def prepare_config_data(cls, runtime_config):
                    return {"value": "test"}


class TestConfigHandlerRegistration:
    """Test ConfigHandler registration with RuntimeContext."""

    def test_handler_auto_registers(self):
        """Test ConfigHandler subclass auto-registers."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

        # Should be in registry
        assert TestHandler in RuntimeContext.config_handler_cls_registry

    def test_handler_accessible_via_getitem(self):
        """Test registered handler accessible via RuntimeContext[Handler]."""

        class TestConfig(BaseModel):
            value: str

        class TestHandler(ConfigHandler[TestConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"value": "test"}

        rc = RuntimeContext()
        handler = rc[TestHandler]

        assert isinstance(handler, TestHandler)
        assert handler.config.value == "test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
