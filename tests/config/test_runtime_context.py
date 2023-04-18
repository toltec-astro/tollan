import tempfile
from pathlib import Path

from tollan.config.models.system_info import SystemInfo
from tollan.config.runtime_context import RuntimeConfigBackend, RuntimeContext
from tollan.utils.log import logger


def test_runtime_config_backend_null_config():
    rcb = RuntimeConfigBackend(None)

    assert rcb.source_config == {}
    assert list(rcb.dict().keys()) == ["runtime_info"]
    assert rcb.runtime_info.system == SystemInfo()


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

    rcb = RuntimeConfigBackend(scfg)
    assert rcb.source_config == scfg
    assert list(rcb.dict().keys()) == ["runtime_info", "a", "b"]
    assert rcb.runtime_info.system == SystemInfo()
    assert rcb.dict(exclude_runtime_info=True) == scfg

    rcb.set_default_config(dcfg)
    assert rcb.source_config == scfg
    assert set(rcb.dict().keys()) == {"runtime_info", "default_key", "a", "b"}
    assert rcb.runtime_info.system == SystemInfo()
    assert rcb.dict(exclude_runtime_info=True) == {
        "a": "a_value",
        "b": {
            "c": 1,
            "d": False,
            "default_key_nested": 0,
        },
        "default_key": "default_value",
    }

    rcb.set_override_config(ocfg)
    assert rcb.source_config == scfg
    assert set(rcb.dict().keys()) == {
        "runtime_info",
        "default_key",
        "override_key",
        "a",
        "b",
    }
    assert rcb.runtime_info.system == SystemInfo()
    assert rcb.dict(exclude_runtime_info=True) == {
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
    logger.debug(f"config:\n{rcb.yaml()}")

    # clear all
    rcb.set_default_config({})
    rcb.set_override_config({})
    assert rcb.source_config == scfg
    assert list(rcb.dict().keys()) == ["runtime_info", "a", "b"]
    assert rcb.runtime_info.system == SystemInfo()
    assert rcb.dict(exclude_runtime_info=True) == scfg

    # update source config
    rcb.sources[0].source.update({"source": "source_value"})
    assert rcb.load_source_config() == {
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
"""
            )
        rcb = RuntimeConfigBackend(config=f)
        assert rcb.dict() == {
            "a": 1,
            "b": {"c": "some_value"},
            "runtime_info": rcb.runtime_info.model_dump(),
        }
    logger.debug(f"config:\n{rcb.yaml()}")


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
"""
            )
        rc = RuntimeContext(f)
        assert rc.config.model_dump() == {
            "a": 1,
            "b": {"c": "some_value"},
            "runtime_info": rc.runtime_info.model_dump(),
        }
    logger.debug(f"config:\n{rc.config_backend.yaml()}")
