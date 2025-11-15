"""Tests for automatic type inference in ConfigHandler and SubConfigKeyTransformer."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel

from tollan.config import ConfigHandler, RuntimeContext, SubConfigKeyTransformer


class TestConfigHandlerAutoInference:
    """Test automatic config_model_cls inference."""

    def test_basic_inference(self):
        """Test config_model_cls is automatically inferred from Generic parameter."""

        class MyConfig(BaseModel):
            x: int = 1
            y: str = "test"

        class MyHandler(ConfigHandler[MyConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"x": 10, "y": "hello"}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        # config_model_cls should be automatically set
        assert MyHandler.config_model_cls == MyConfig

    def test_inference_with_usage(self):
        """Test inferred config_model_cls works in practice."""

        class AppConfig(BaseModel):
            debug: bool = False
            port: int = 8000

        class AppHandler(ConfigHandler[AppConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {"debug": True, "port": 3000}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        rc = RuntimeContext()
        handler = AppHandler(rc)
        config = handler.config

        assert isinstance(config, AppConfig)
        assert config.debug is True
        assert config.port == 3000

    def test_manual_override_disallowed(self):
        """Test manual config_model_cls definition is now disallowed."""

        class Config1(BaseModel):
            x: int = 1

        class Config2(BaseModel):
            y: str = "test"

        # Manual override should raise TypeError
        with pytest.raises(TypeError, match="explicitly sets 'config_model_cls'"):

            class MyHandler(ConfigHandler[Config1]):
                config_model_cls = (
                    Config2  # Should be disallowed  # type: ignore[assignment]
                )

                @classmethod
                def prepare_config_data(cls, runtime_config):
                    return {"y": "manual"}

                @classmethod
                def prepare_runtime_config_data(cls, config_data):
                    return config_data

    def test_multiple_handlers_independent(self):
        """Test multiple handlers get correct independent inference."""

        class Config1(BaseModel):
            a: int = 1

        class Config2(BaseModel):
            b: str = "x"

        class Config3(BaseModel):
            c: float = 1.0

        class Handler1(ConfigHandler[Config1]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        class Handler2(ConfigHandler[Config2]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        class Handler3(ConfigHandler[Config3]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        assert Handler1.config_model_cls == Config1
        assert Handler2.config_model_cls == Config2
        assert Handler3.config_model_cls == Config3

    def test_no_generic_parameter_disallowed(self):
        # Even without Generic parameter, explicit config_model_cls disallowed
        with pytest.raises(TypeError, match="explicitly sets 'config_model_cls'"):

            class PlainHandler(ConfigHandler):
                config_model_cls = dict

                @classmethod
                def prepare_config_data(cls, runtime_config):
                    return {}

                @classmethod
                def prepare_runtime_config_data(cls, config_data):
                    return config_data

    def test_inheritance_chain(self):
        """Test inference works through inheritance chain."""

        class MyConfig(BaseModel):
            value: int = 1

        class BaseHandler(ConfigHandler[MyConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        class DerivedHandler(BaseHandler):
            pass

        # Both should have the inferred config_model_cls
        assert BaseHandler.config_model_cls == MyConfig
        assert DerivedHandler.config_model_cls == MyConfig


class TestSubConfigKeyTransformerAutoInference:
    """Test automatic subconfig_key inference."""

    def test_basic_literal_inference(self):
        """Test subconfig_key is inferred from Literal parameter."""

        class MyConfig(BaseModel):
            x: int = 1

        class MyHandler(
            SubConfigKeyTransformer[Literal["mykey"]],
            ConfigHandler[MyConfig],
        ):
            pass

        assert MyHandler.subconfig_key == "mykey"
        assert MyHandler.config_model_cls == MyConfig

    def test_inference_with_usage(self):
        """Test inferred subconfig_key works in practice."""

        class DatabaseConfig(BaseModel):
            host: str
            port: int

        class DatabaseHandler(
            SubConfigKeyTransformer[Literal["database"]],
            ConfigHandler[DatabaseConfig],
        ):
            pass

        rc = RuntimeContext()
        rc.set_default_config(
            {"database": {"host": "localhost", "port": 5432}},
        )

        handler = DatabaseHandler(rc)
        config = handler.config

        assert isinstance(config, DatabaseConfig)
        assert config.host == "localhost"
        assert config.port == 5432

    def test_manual_override_disallowed(self):
        """Test manual subconfig_key is now disallowed."""

        class MyConfig(BaseModel):
            x: int = 1

        # Manual override should raise TypeError
        with pytest.raises(TypeError, match="explicitly sets 'subconfig_key'"):

            class MyHandler(
                SubConfigKeyTransformer[Literal["literal_key"]],
                ConfigHandler[MyConfig],
            ):
                subconfig_key = "manual_key"  # Should be disallowed

    def test_multiple_transformers_independent(self):
        """Test multiple transformers get correct independent inference."""

        class C1(BaseModel):
            x: int = 1

        class C2(BaseModel):
            y: str = "a"

        class C3(BaseModel):
            z: float = 1.0

        class H1(SubConfigKeyTransformer[Literal["one"]], ConfigHandler[C1]):
            pass

        class H2(SubConfigKeyTransformer[Literal["two"]], ConfigHandler[C2]):
            pass

        class H3(SubConfigKeyTransformer[Literal["three"]], ConfigHandler[C3]):
            pass

        assert H1.subconfig_key == "one" and H1.config_model_cls == C1
        assert H2.subconfig_key == "two" and H2.config_model_cls == C2
        assert H3.subconfig_key == "three" and H3.config_model_cls == C3

    def test_complex_config_keys(self):
        """Test with various key formats."""

        class Config(BaseModel):
            x: int = 1

        class DashHandler(
            SubConfigKeyTransformer[Literal["my-key"]],
            ConfigHandler[Config],
        ):
            pass

        class UnderscoreHandler(
            SubConfigKeyTransformer[Literal["my_key"]],
            ConfigHandler[Config],
        ):
            pass

        class DotHandler(
            SubConfigKeyTransformer[Literal["my.key"]],
            ConfigHandler[Config],
        ):
            pass

        assert DashHandler.subconfig_key == "my-key"
        assert UnderscoreHandler.subconfig_key == "my_key"
        assert DotHandler.subconfig_key == "my.key"


class TestCombinedAutoInference:
    """Test both automatic inferences working together."""

    def test_zero_boilerplate_handler(self):
        """Test handler with no manual definitions works completely."""

        class ApiConfig(BaseModel):
            endpoint: str
            timeout: int = 30

        class ApiHandler(
            SubConfigKeyTransformer[Literal["api"]],
            ConfigHandler[ApiConfig],
        ):
            pass  # No manual definitions at all!

        # Both should be inferred
        assert ApiHandler.config_model_cls == ApiConfig
        assert ApiHandler.subconfig_key == "api"

    def test_full_workflow(self):
        """Test complete workflow with inferred types."""

        class CacheConfig(BaseModel):
            url: str
            ttl: int

        class LogConfig(BaseModel):
            level: str

        class CacheHandler(
            SubConfigKeyTransformer[Literal["cache"]],
            ConfigHandler[CacheConfig],
        ):
            pass

        class LogHandler(
            SubConfigKeyTransformer[Literal["logging"]],
            ConfigHandler[LogConfig],
        ):
            pass

        # Setup runtime context
        rc = RuntimeContext()
        rc.set_default_config(
            {
                "cache": {"url": "redis://localhost", "ttl": 3600},
                "logging": {"level": "INFO"},
            },
        )

        # Use handlers
        cache_handler = CacheHandler(rc)
        log_handler = LogHandler(rc)

        cache_config = cache_handler.config
        log_config = log_handler.config

        assert cache_config.url == "redis://localhost"
        assert cache_config.ttl == 3600
        assert log_config.level == "INFO"

    def test_mixed_inference_manual_disallowed(self):
        """Test that manual overrides are disallowed even when mixing."""

        class Config1(BaseModel):
            x: int = 1

        class Config2(BaseModel):
            y: str = "test"

        # Manual subconfig_key should be disallowed
        with pytest.raises(TypeError, match="explicitly sets 'subconfig_key'"):

            class Handler1(
                SubConfigKeyTransformer[Literal["auto"]],
                ConfigHandler[Config1],
            ):
                subconfig_key = "manual"  # Should be disallowed

        # Manual config_model_cls should be disallowed
        with pytest.raises(TypeError, match="explicitly sets 'config_model_cls'"):

            class Handler2(
                SubConfigKeyTransformer[Literal["auto"]],
                ConfigHandler[Config1],
            ):
                config_model_cls = (
                    Config2  # Should be disallowed  # type: ignore[assignment]
                )


class TestRuntimeContextIntegration:
    """Test automatic inference with RuntimeContext."""

    def test_handler_registration(self):
        """Test auto-inferred handlers register correctly."""

        class TestConfig(BaseModel):
            value: int = 1

        class TestHandler(
            SubConfigKeyTransformer[Literal["test"]],
            ConfigHandler[TestConfig],
        ):
            pass

        rc = RuntimeContext()
        rc.set_default_config({"test": {"value": 42}})

        # Should be able to retrieve by class
        handler = rc[TestHandler]
        assert isinstance(handler, TestHandler)
        assert handler.config.value == 42

    def test_multiple_handlers_in_context(self):
        """Test multiple auto-inferred handlers in same context."""

        class DbConfig(BaseModel):
            host: str

        class ApiConfig(BaseModel):
            endpoint: str

        class CacheConfig(BaseModel):
            url: str

        class DbHandler(
            SubConfigKeyTransformer[Literal["database"]],
            ConfigHandler[DbConfig],
        ):
            pass

        class ApiHandler(
            SubConfigKeyTransformer[Literal["api"]],
            ConfigHandler[ApiConfig],
        ):
            pass

        class CacheHandler(
            SubConfigKeyTransformer[Literal["cache"]],
            ConfigHandler[CacheConfig],
        ):
            pass

        rc = RuntimeContext()
        rc.set_default_config(
            {
                "database": {"host": "db.example.com"},
                "api": {"endpoint": "https://api.example.com"},
                "cache": {"url": "redis://cache.example.com"},
            },
        )

        # Get multiple handlers at once
        db, api, cache = rc[DbHandler, ApiHandler, CacheHandler]

        assert db.config.host == "db.example.com"
        assert api.config.endpoint == "https://api.example.com"
        assert cache.config.url == "redis://cache.example.com"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_no_type_params_explicit_disallowed(self):
        """Test handler without type params but with explicit attribute
        is disallowed."""

        # Even without type params, explicit config_model_cls should be disallowed
        with pytest.raises(TypeError, match="explicitly sets 'config_model_cls'"):

            class PlainHandler(ConfigHandler):
                config_model_cls = dict

                @classmethod
                def prepare_config_data(cls, runtime_config):
                    return {}

                @classmethod
                def prepare_runtime_config_data(cls, config_data):
                    return config_data

    def test_invalid_generic_param_explicit_disallowed(self):
        """Test explicit attribute disallowed with invalid generic param."""

        # Even with invalid generic param, explicit config_model_cls disallowed
        with pytest.raises(TypeError, match="explicitly sets 'config_model_cls'"):

            class Handler(ConfigHandler[int]):  # type: ignore[type-var]
                config_model_cls = dict  # type: ignore[assignment]

                @classmethod
                def prepare_config_data(cls, runtime_config):
                    return {}

                @classmethod
                def prepare_runtime_config_data(cls, config_data):
                    return config_data

    def test_abstract_handler_no_inference(self):
        """Test abstract base handlers work correctly."""
        from abc import ABC, abstractmethod

        class MyConfig(BaseModel):
            x: int = 1

        class AbstractHandler(ConfigHandler[MyConfig], ABC):
            @classmethod
            @abstractmethod
            def custom_method(cls):
                raise NotImplementedError

        class ConcreteHandler(AbstractHandler):
            @classmethod
            def custom_method(cls):
                return "implemented"

            @classmethod
            def prepare_config_data(cls, runtime_config):
                return {}

            @classmethod
            def prepare_runtime_config_data(cls, config_data):
                return config_data

        # Both should have inferred config_model_cls
        assert AbstractHandler.config_model_cls == MyConfig
        assert ConcreteHandler.config_model_cls == MyConfig
