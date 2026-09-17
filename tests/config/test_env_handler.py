"""Environment handlers capture one namespace without mutating the process."""

import os
from typing import assert_type

import pytest
from pydantic import ValidationError

from tollan.config import EnvHandler, RuntimeConfig, RuntimeContext
from tollan.config.sources import EnvFileConfigSource


@pytest.mark.parametrize("namespace", ["_env", "process", "process.env", ""])
def test_handler_reads_selected_namespace_and_keeps_snapshot(tmp_path, namespace):
    path = tmp_path / "settings.env"
    path.write_text("TOLLAN_ENV_TEST=original\nEMPTY=\nUNSET\n")
    environ = dict(os.environ)
    rc, handler = RuntimeContext.from_cli(
        env_paths=[path], env_namespace=namespace, return_env_handler=True
    )
    assert isinstance(handler, EnvHandler)
    assert handler.as_environ() == {"TOLLAN_ENV_TEST": "original", "EMPTY": ""}
    rc.update_override_config({namespace: {"TOLLAN_ENV_TEST": "updated"}})
    assert handler.as_environ()["TOLLAN_ENV_TEST"] == "original"
    assert handler.recreate().as_environ()["TOLLAN_ENV_TEST"] == "updated"
    assert handler.runtime_info is not rc.runtime_info
    exported = handler.as_environ()
    exported["TOLLAN_ENV_TEST"] = "caller edit"
    assert handler.as_environ()["TOLLAN_ENV_TEST"] == "original"
    assert dict(os.environ) == environ


def test_handler_uses_merged_values_and_converts_without_mutating_runtime(tmp_path):
    config = tmp_path / "settings.yaml"
    config.write_text("_env: {PORT: 8000, YAML_ONLY: true}\nother: ignored\n")
    env = tmp_path / "settings.env"
    env.write_text("PORT=9000\nENV_ONLY=yes\n")
    rc, handler = RuntimeContext.from_cli(
        config_paths=[config],
        env_paths=[env],
        cli_args=["--_env.PORT", "10000"],
        return_env_handler=True,
    )
    assert handler is not None
    assert handler.as_environ() == {
        "PORT": "10000",
        "YAML_ONLY": "True",
        "ENV_ONLY": "yes",
    }
    assert rc.config_dict["_env"] == {
        "PORT": 10000,
        "YAML_ONLY": True,
        "ENV_ONLY": "yes",
    }


@pytest.mark.parametrize("namespace", ["_env", "process"])
def test_temporary_handlers_keep_namespace_and_runtime_isolation(namespace):
    rc, handler = RuntimeContext.from_cli(
        env_namespace=namespace, return_env_handler=True
    )
    assert handler is not None
    assert handler.as_environ() == {}
    with handler.temporary_config(
        defaults={"DEFAULT": "yes"},
        overrides={"VALUE": 42},
        validation_context={"profile": "local"},
    ) as other:
        assert other.as_environ() == {"DEFAULT": "yes", "VALUE": "42"}
        assert other.recreate().as_environ() == other.as_environ()
        assert other.runtime_info.validation_context == {"profile": "local"}
    with handler.temporary_runtime_config(
        overrides={namespace: {"VALUE": "runtime"}, "ignored": True}
    ) as other:
        assert other.as_environ() == {"VALUE": "runtime"}
    assert handler.as_environ() == {}
    assert namespace not in rc.config_dict


@pytest.mark.parametrize("return_handler", [False, True])
@pytest.mark.parametrize("namespace", [None, "process"])
def test_only_requested_namespaced_handler_loads_files(
    tmp_path, monkeypatch, return_handler, namespace
):
    path = tmp_path / "settings.env"
    path.write_text("VALUE=test\n")
    reads = []
    read = EnvFileConfigSource._read

    def count_read(source):
        reads.append(source.source)
        return read(source)

    monkeypatch.setattr(EnvFileConfigSource, "_read", count_read)
    result = RuntimeContext.from_cli(
        env_paths=[path], env_namespace=namespace, return_env_handler=return_handler
    )
    if return_handler:
        assert isinstance(result, tuple)
        rc, handler = result
        assert (handler is None) == (namespace is None)
    else:
        assert isinstance(result, RuntimeContext)
        rc, handler = result, None
    assert reads == ([path] if handler is not None else [])
    config = rc.config_dict
    assert (config if namespace is None else config[namespace])["VALUE"] == "test"
    if handler is not None:
        handler.as_environ()
        handler.recreate()
    assert reads == [path]


def test_explicit_source_namespaces_are_not_collected(tmp_path):
    env = tmp_path / "settings.env"
    env.write_text("VALUE=test\n")
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        "- source: settings.env\n  namespace: elsewhere\n"
        "- source: settings.env\n  namespace: null\n"
    )
    rc, handler = RuntimeContext.from_cli(
        config_paths=[sources], env_namespace="process", return_env_handler=True
    )
    assert handler is not None
    assert handler.as_environ() == {}
    assert rc.config_dict["elsewhere"] == {"VALUE": "test"}
    assert rc.config_dict["VALUE"] == "test"


@pytest.mark.parametrize("data", [None, "not a mapping", ["entry"], {1: "value"}])
def test_invalid_namespace_mapping_fails_on_handler_construction(data):
    rc = RuntimeContext()
    rc.update_override_config({"_env": data})
    with pytest.raises(ValidationError):
        EnvHandler(rc)


def test_custom_namespace_classes_are_not_retained_in_global_registry():
    registry = set(RuntimeContext.config_handler_cls_registry)
    for namespace in ("process", "other", "process"):
        rc, handler = RuntimeContext.from_cli(
            env_namespace=namespace, return_env_handler=True
        )
        assert handler is not None
        assert type(handler) not in RuntimeContext.config_handler_cls_registry
        assert rc[EnvHandler].as_environ() == {}
    assert RuntimeContext.config_handler_cls_registry == registry


def test_factory_return_types_and_runtime_subclasses():
    class CustomRuntime(RuntimeContext):
        pass

    assert_type(CustomRuntime.from_cli(), CustomRuntime)
    assert_type(CustomRuntime.from_cli(return_env_handler=False), CustomRuntime)
    rc, handler = assert_type(
        CustomRuntime.from_cli(return_env_handler=True),
        tuple[CustomRuntime, EnvHandler | None],
    )
    assert isinstance(rc, CustomRuntime)
    assert handler is not None
    assert handler.config.model_dump() == {}


def test_handler_accepts_typed_runtime_config_with_other_extra_fields():
    class Settings(RuntimeConfig):
        process: dict[str, int]

    class CustomRuntime(RuntimeContext[Settings]):
        pass

    rc, handler = CustomRuntime.from_cli(
        cli_args=["--process.PORT", "8000", "--other", "true"],
        env_namespace="process",
        return_env_handler=True,
    )
    assert isinstance(rc.config, Settings)
    assert handler is not None
    assert handler.as_environ() == {"PORT": "8000"}


def test_namespace_can_match_model_method_without_reading_that_method():
    _, empty = RuntimeContext.from_cli(
        env_namespace="model_dump", return_env_handler=True
    )
    assert empty is not None
    assert empty.as_environ() == {}
    _, populated = RuntimeContext.from_cli(
        cli_args=["--model_dump.PORT", "8000"],
        env_namespace="model_dump",
        return_env_handler=True,
    )
    assert populated is not None
    assert populated.as_environ() == {"PORT": "8000"}
