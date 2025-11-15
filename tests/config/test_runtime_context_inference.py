"""Test automatic inference of runtime_config_cls from RuntimeConfigT."""

from __future__ import annotations

import pytest
from pydantic import Field

from tollan.config import RuntimeConfig, RuntimeContext, RuntimeInfo


def test_default_runtime_context_uses_base_runtime_config():
    """Test that default RuntimeContext uses RuntimeConfig."""
    rc = RuntimeContext()

    # Default should be RuntimeConfig
    assert rc.runtime_config_cls is RuntimeConfig
    assert isinstance(rc.config, RuntimeConfig)


def test_custom_runtime_config_inference():
    """Test automatic inference of custom RuntimeConfig from type parameter."""

    # Use default RuntimeInfo (no custom subclass)
    class AppRuntimeConfig(RuntimeConfig):
        database_url: str = "sqlite:///app.db"
        debug: bool = False

    class AppRuntimeContext(RuntimeContext[AppRuntimeConfig]):
        pass

    # Should automatically infer runtime_config_cls
    assert AppRuntimeContext.runtime_config_cls is AppRuntimeConfig

    # Create instance and verify it uses the custom config
    rc = AppRuntimeContext()
    rc.set_default_config(
        {
            "database_url": "postgresql://localhost/mydb",
            "debug": True,
        },
    )

    config = rc.config
    assert isinstance(config, AppRuntimeConfig)
    assert config.database_url == "postgresql://localhost/mydb"
    assert config.debug is True
    assert isinstance(config.runtime_info, RuntimeInfo)


def test_manual_runtime_config_cls_disallowed():
    """Test that manual runtime_config_cls definition raises TypeError."""

    class Config1(RuntimeConfig):
        value: int = 1

    class Config2(RuntimeConfig):
        value: int = 2

    # Should raise TypeError when trying to set runtime_config_cls explicitly
    with pytest.raises(TypeError, match="explicitly sets 'runtime_config_cls'"):

        class MyContext(RuntimeContext[Config1]):
            runtime_config_cls = Config2  # Not allowed! # type: ignore[assignment]


def test_nested_runtime_config_inheritance():
    """Test that inference works through inheritance chains."""

    class BaseConfig(RuntimeConfig):
        base_field: str = "base"

    class DerivedConfig(BaseConfig):
        derived_field: str = "derived"

    class BaseContext(RuntimeContext[BaseConfig]):
        pass

    class DerivedContext(BaseContext):
        # Should inherit the inferred runtime_config_cls
        pass

    # Base context should infer BaseConfig
    assert BaseContext.runtime_config_cls is BaseConfig

    # Derived context should inherit parent's runtime_config_cls
    assert DerivedContext.runtime_config_cls is BaseConfig

    # But we can override with a new type parameter
    class OverrideContext(RuntimeContext[DerivedConfig]):
        pass

    assert OverrideContext.runtime_config_cls is DerivedConfig


def test_runtime_config_with_extra_fields():
    """Test custom RuntimeConfig with extra fields works correctly."""

    class CustomConfig(RuntimeConfig):
        # Define specific fields
        api_key: str = Field(default="", description="API key")
        timeout: int = Field(default=30, description="Request timeout")

    class CustomContext(RuntimeContext[CustomConfig]):
        pass

    assert CustomContext.runtime_config_cls is CustomConfig

    rc = CustomContext()
    rc.set_default_config(
        {
            "api_key": "secret123",
            "timeout": 60,
            "extra_field": "allowed",  # extra="allow" should work
        },
    )

    config = rc.config
    assert isinstance(config, CustomConfig)
    assert config.api_key == "secret123"
    assert config.timeout == 60
    # Extra fields should be accessible
    assert config.extra_field == "allowed"  # type: ignore[attr-defined]


def test_from_cli_with_custom_runtime_config():
    """Test from_cli factory method works with custom RuntimeConfig."""

    class AppConfig(RuntimeConfig):
        pass

    class AppContext(RuntimeContext[AppConfig]):
        pass

    # from_cli should work with custom config
    # CLI args create nested structure: {"server": {"host": ..., "port": ...}}
    # These go into extra fields since AppConfig doesn't define them
    rc = AppContext.from_cli(
        cli_args=["--server.host", "127.0.0.1", "--server.port", "9000"],
    )

    config = rc.config
    assert isinstance(config, AppConfig)
    # CLI args are in extra fields as nested dict
    assert config.server["host"] == "127.0.0.1"  # type: ignore[attr-defined, index]
    assert config.server["port"] == 9000  # type: ignore[attr-defined, index]
