import tempfile
from pathlib import Path

from tollan.config.models.system_info import SystemInfo
from tollan.config.runtime_context import ConfigBackend, RuntimeContext, RuntimeInfo
from tollan.utils.log import logger


def test_class_vars():
    assert ConfigBackend.runtime_info_model_cls is RuntimeInfo
    assert RuntimeContext.config_backend_cls is ConfigBackend


def test_runtime_config_backend_null_config():
    cb = ConfigBackend(None)

    assert cb.source_config == {}
    assert list(cb.dict().keys()) == ["runtime_info"]
    assert cb.runtime_info.system == SystemInfo()


def test_runtime_config_backend_dict_config():
    scfg = {
        "a": "a_value",
        "b": {
            "c": 1,
            "d": False,
        },
    }
    dcfg = {
        "default_key": "default_value",
        "b": {
            "c": 0,
            "default_key_nested": 0,
        },
    }
    ocfg = {
        "override_key": "override_value",
        "b": {
            "c": 2,
            "override_key_nested": 1,
        },
    }

    cb = ConfigBackend(scfg)
    assert cb.source_config == scfg
    assert list(cb.dict().keys()) == ["runtime_info", "a", "b"]
    assert cb.runtime_info.system == SystemInfo()
    assert cb.dict(exclude_runtime_info=True) == scfg

    cb.set_default_config(dcfg)
    assert cb.source_config == scfg
    assert set(cb.dict().keys()) == {"runtime_info", "default_key", "a", "b"}
    assert cb.runtime_info.system == SystemInfo()
    assert cb.dict(exclude_runtime_info=True) == {
        "a": "a_value",
        "b": {
            "c": 1,
            "d": False,
            "default_key_nested": 0,
        },
        "default_key": "default_value",
    }

    cb.set_override_config(ocfg)
    assert cb.source_config == scfg
    assert set(cb.dict().keys()) == {
        "runtime_info",
        "default_key",
        "override_key",
        "a",
        "b",
    }
    assert cb.runtime_info.system == SystemInfo()
    assert cb.dict(exclude_runtime_info=True) == {
        "a": "a_value",
        "b": {
            "c": 2,
            "d": False,
            "default_key_nested": 0,
            "override_key_nested": 1,
        },
        "default_key": "default_value",
        "override_key": "override_value",
    }
    logger.debug(f"config:\n{cb.yaml()}")

    # clear all
    cb.set_default_config({})
    cb.set_override_config({})
    assert cb.source_config == scfg
    assert list(cb.dict().keys()) == ["runtime_info", "a", "b"]
    assert cb.runtime_info.system == SystemInfo()
    assert cb.dict(exclude_runtime_info=True) == scfg

    # update source config
    cb.sources[0].source.update({"source": "source_value"})  # type: ignore
    assert cb.load_source_config() == {
        "a": "a_value",
        "b": {
            "c": 1,
            "d": False,
        },
        "source": "source_value",
    }


def test_runtime_config_backend_file_config():
    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        f = tmp / "some_config.yaml"
        with f.open("w") as fo:
            fo.write(
                """
---
a: 1
b:
  c: 'some_value'
""",
            )
        cb = ConfigBackend(config=f)
        assert cb.dict() == {
            "a": 1,
            "b": {"c": "some_value"},
            "runtime_info": cb.runtime_info.model_dump(),
        }
    logger.debug(f"config:\n{cb.yaml()}")


def test_runtime_context():
    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        f = tmp / "some_config.yaml"
        with f.open("w") as fo:
            fo.write(
                """
---
a: 1
b:
  c: 'some_value'
""",
            )
        rc = RuntimeContext(f)
        assert rc.config.model_dump() == {
            "a": 1,
            "b": {"c": "some_value"},
            "runtime_info": rc.runtime_info.model_dump(),
        }
    logger.debug(f"config:\n{rc.config_backend.yaml()}")
