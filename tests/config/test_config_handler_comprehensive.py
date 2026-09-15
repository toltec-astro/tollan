"""Tests for eager domain handlers and isolated runtime variants."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from threading import Barrier
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tollan.config import ConfigHandler, RuntimeContext, SubConfigKeyTransformer
from tollan.config.types import AbsAnyPath


class DomainConfig(BaseModel):
    value: str
    limit: int = Field(default=10, gt=0)


class DomainHandler(
    SubConfigKeyTransformer[Literal["domain"]],
    ConfigHandler[DomainConfig],
):
    @cached_property
    def resource(self):
        return {"value": self.config.value}


@pytest.fixture
def runtime():
    return RuntimeContext(
        config_sources=[
            {"format": "dict", "source": {"domain": {"value": "original"}}, "order": 0}
        ]
    )


class TestConfigHandlerBasics:
    def test_handler_initialization_is_eager(self, runtime):
        calls = []

        class Handler(DomainHandler):
            def _load_config(self):
                calls.append(self)
                assert super()._load_config() is None

        handler = Handler(runtime)
        assert calls == [handler]
        assert handler._rc is runtime
        assert handler.config is handler._config
        assert handler.config.value == "original"
        assert "resource" not in handler.__dict__
        assert not hasattr(handler, "rc")
        assert not hasattr(handler, "runtime_config")
        assert handler.runtime_info is runtime.config.runtime_info

    def test_runtime_info_is_captured_before_first_access(self, runtime):
        handler = DomainHandler(runtime)
        info = runtime.runtime_info
        runtime.update_override_config({"runtime_info": {"cmd": "later invocation"}})
        assert handler.runtime_info is info
        other = handler.recreate()
        assert other.runtime_info is runtime.runtime_info
        assert other.runtime_info is not info
        assert other.runtime_info.cmd == "later invocation"
        assert handler.runtime_info.config_sources is runtime.config_sources

    def test_runtime_info_retains_context_after_runtime_scope_exits(self, runtime):
        with runtime.set_context({"observation": 42}):
            handler = DomainHandler(runtime)
        assert runtime.runtime_info.validation_context == {}
        assert handler.runtime_info.validation_context == {"observation": 42}
        assert handler.recreate().runtime_info.validation_context == {}

    def test_config_is_stable_before_first_access(self, runtime):
        handler = DomainHandler(runtime)
        runtime.update_override_config({"domain": {"value": "later"}})
        assert handler.config.value == "original"
        assert handler.recreate().config.value == "later"

    def test_invalid_config_fails_at_construction(self):
        with pytest.raises(ValidationError, match="value"):
            DomainHandler(RuntimeContext())

    def test_handler_must_implement_prepare_config_data(self):
        class BadHandler(ConfigHandler[DomainConfig]):
            pass

        with pytest.raises(NotImplementedError, match="prepare_config_data"):
            BadHandler(RuntimeContext())

    def test_handler_must_implement_prepare_runtime_config_data(self, runtime):
        class ReadOnlyHandler(ConfigHandler[DomainConfig]):
            @classmethod
            def prepare_config_data(cls, runtime_config):
                return runtime_config.domain

        handler = ReadOnlyHandler(runtime)
        with (
            pytest.raises(NotImplementedError, match="prepare_runtime_config_data"),
            handler.temporary_config(overrides={"value": "new"}),
        ):
            pass

    def test_recreate_uses_concrete_constructor(self, runtime):
        calls = []

        class Handler(DomainHandler):
            def __init__(self, runtime_context):
                super().__init__(runtime_context)
                calls.append(self)

        handler = Handler(runtime)
        other = handler.recreate()
        assert calls == [handler, other]
        assert type(other) is Handler
        assert other is not handler
        assert other.config is not handler.config

    def test_cached_resource_belongs_to_handler(self, runtime):
        handler = DomainHandler(runtime)
        resource = handler.resource
        runtime.update_override_config({"domain": {"value": "later"}})
        other = handler.recreate()
        assert handler.resource is resource
        assert handler.resource["value"] == "original"
        assert other.resource == {"value": "later"}
        assert other.resource is not resource


class TestConfigHandlerVariants:
    def test_domain_overrides_and_defaults(self, runtime):
        handler = DomainHandler(runtime)
        original_config = runtime.config
        with handler.temporary_config(
            defaults={"value": "default", "limit": 20},
            overrides={"value": "variant"},
        ) as other:
            assert other is not handler
            assert other.config == DomainConfig(value="variant", limit=20)
            assert handler.config.value == "original"
            assert runtime.config is original_config
        assert runtime.config is original_config
        assert "limit" not in runtime.config_dict["domain"]

    def test_runtime_patch_goes_through_extraction(self, runtime):
        handler = DomainHandler(runtime)
        with handler.temporary_runtime_config(
            overrides={"domain": {"limit": 25}, "other_domain": {"enabled": True}}
        ) as other:
            assert other.config == DomainConfig(value="original", limit=25)
            assert other._rc.config_dict["other_domain"] == {"enabled": True}
        assert "other_domain" not in runtime.config_dict

    def test_nested_scopes_are_independent(self, runtime):
        handler = DomainHandler(runtime)
        resource = handler.resource
        with handler.temporary_config(overrides={"value": "outer"}) as outer:
            with outer.temporary_config(overrides={"limit": 30}) as inner:
                assert inner.config == DomainConfig(value="outer", limit=30)
                assert outer.config == DomainConfig(value="outer")
                assert handler.config == DomainConfig(value="original")
            assert outer.config.value == "outer"
        assert handler.resource is resource

    def test_variant_validation_failure_does_not_change_parent(self, runtime):
        handler = DomainHandler(runtime)
        config = runtime.config
        with (
            pytest.raises(ValidationError, match="limit"),
            handler.temporary_config(overrides={"limit": -1}),
        ):
            pass
        assert runtime.config is config
        assert handler.config.limit == 10

    def test_exception_in_scope_does_not_change_parent(self, runtime):
        handler = DomainHandler(runtime)
        config = runtime.config

        def use_variant():
            with handler.temporary_config(overrides={"value": "variant"}) as other:
                assert other.config.value == "variant"
                msg = "processing failed"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="processing failed"):
            use_variant()
        assert runtime.config is config
        assert handler.config.value == "original"

    def test_variant_uses_current_runtime_not_a_model_dump(self, runtime):
        handler = DomainHandler(runtime)
        runtime.update_override_config({"domain": {"value": "later"}})
        with handler.temporary_config(overrides={"limit": 30}) as other:
            assert other.config == DomainConfig(value="later", limit=30)
        assert handler.config.value == "original"

    def test_raw_paths_are_revalidated_with_variant_context(self, tmp_path):
        class Config(BaseModel):
            path: AbsAnyPath

        class Handler(
            SubConfigKeyTransformer[Literal["domain"]], ConfigHandler[Config]
        ):
            pass

        runtime = RuntimeContext().with_config(
            overrides={"domain": {"path": "relative.txt"}},
            validation_context={"rootpath": tmp_path / "first", "observation": 1},
        )
        handler = Handler(runtime)
        with handler.temporary_config(
            validation_context={"rootpath": tmp_path / "second"}
        ) as other:
            assert other.config.path == tmp_path / "second" / "relative.txt"
            assert other.runtime_info.validation_context["observation"] == 1
            assert (
                other.runtime_info.validation_context["rootpath"] == tmp_path / "second"
            )
        assert handler.config.path == tmp_path / "first" / "relative.txt"
        assert handler.runtime_info.validation_context["rootpath"] == tmp_path / "first"
        assert other.runtime_info.validation_context["rootpath"] == tmp_path / "second"
        assert runtime.config_dict["domain"]["path"] == "relative.txt"

    def test_opaque_values_are_not_copied(self):
        class Opaque:
            def __deepcopy__(self, memo):
                pytest.fail("opaque resources must not be copied")

        class Config(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            resource: Any
            limit: int = 10

        class Handler(
            SubConfigKeyTransformer[Literal["domain"]], ConfigHandler[Config]
        ):
            pass

        resource = Opaque()
        handler = Handler(
            RuntimeContext().with_config(overrides={"domain": {"resource": resource}})
        )
        with handler.temporary_config(overrides={"limit": 20}) as other:
            assert other.config.resource is resource
        assert handler.config.resource is resource

    def test_concurrent_scopes_do_not_swap_shared_runtime(self, runtime):
        handler = DomainHandler(runtime)
        rendezvous = Barrier(2)

        def run(value):
            with handler.temporary_config(
                overrides={"value": value}, validation_context={"observation": value}
            ) as other:
                rendezvous.wait(timeout=5)
                return other.config.value, other.runtime_info.validation_context

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, ["first", "second"]))
        assert results == [
            ("first", {"observation": "first"}),
            ("second", {"observation": "second"}),
        ]
        assert handler.config.value == "original"
        assert runtime.runtime_info.validation_context == {}


class TestConfigHandlerTypeInference:
    """Test ConfigHandler config_model_cls inference."""

    def test_infers_config_model_cls_from_generic(self):
        """Test config_model_cls is derived from its type-variable binding."""

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
                config_model_cls: type[BaseModel] = ConfigB  # pyright: ignore[reportIncompatibleVariableOverride]  # ty: ignore[invalid-attribute-override]  # Should be disallowed

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
