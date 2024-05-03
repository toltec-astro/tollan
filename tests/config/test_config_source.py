from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from astropy.io.registry import IORegistryError

from tollan.config.models.config_source import (
    ConfigSource,
    ConfigSourceList,
    config_source_io_registry,
)
from tollan.utils.log import logger

_yaml_content = """
a: b
c:
  d: 1
e: [0, true]
"""
_yaml_content_dict = {"a": "b", "c": {"d": 1}, "e": [0, True]}


def test_config_source_io_registry():
    r = config_source_io_registry

    with tempfile.TemporaryDirectory() as tmp:
        f0 = Path(tmp) / "a.yaml"
        f1 = Path(tmp) / "a.not_yaml"
        with f0.open("w") as fo:
            fo.write(_yaml_content)
        with f1.open("w") as fo:
            fo.write(_yaml_content)
        assert r.identify_format("read", dict, f0, None, (), {}) == ["yaml"]
        logger.debug(f"yaml_content: {r.read(dict, f0)}")
        assert r.read(dict, f0) == _yaml_content_dict
        assert not r.identify_format("read", dict, f1, None, (), {})
        with pytest.raises(IORegistryError):
            assert r.read(dict, f1) == _yaml_content_dict
        assert r.read(dict, f1, format="yaml") == _yaml_content_dict


def test_config_source_file():
    with tempfile.TemporaryDirectory() as tmp:
        f0 = Path(tmp) / "a.yaml"
        with f0.open("w") as fo:
            fo.write(_yaml_content)
        cs = ConfigSource.model_validate({"order": 1, "source": f0, "name": "f0"})
        logger.debug(f"config_source={cs!r}")
        assert cs.order == 1
        assert cs.source == f0.resolve()
        assert cs.format == "yaml"
        assert cs.enabled
        assert cs.enable_if is None
        assert cs.is_file()
        assert cs.load() == _yaml_content_dict
        # f1 = Path(tmp) / "b.yaml"
        cs.dump({"updated": True})
        with f0.open("r") as fo:
            logger.debug(f"file content:\n{fo.read()}")
        assert cs.load() == {"updated": True}
        assert cs.name == "f0"


def test_config_source_dict():
    data = {"in_memory": True}
    cs = ConfigSource.model_validate({"order": 1, "source": data})
    logger.debug(f"config_source={cs!r}")
    assert cs.order == 1
    assert cs.source == data
    assert cs.format == "dict"
    assert cs.enabled
    assert cs.enable_if is None
    assert not cs.is_file()
    assert cs.load() == data
    cs.dump({"updated": True})
    assert cs.source == {"updated": True}
    assert cs.name is None


def test_config_source_cli_args():
    data = ["--in_memory", "--nested", "[1, 2]"]
    cs = ConfigSource.model_validate({"order": 1, "source": data})
    logger.debug(f"config_source={cs!r}")
    assert cs.order == 1
    assert cs.source == data
    assert cs.format == "cli_args"
    assert cs.enabled
    assert cs.enable_if is None
    assert not cs.is_file()
    assert cs.load() == {"in_memory": True, "nested": [1, 2]}
    cs.dump({"updated": True})
    assert cs.source == {"updated": True}
    assert cs.name is None


def test_config_source_config_source_list():
    data = {"in_memory": True}
    csl0 = ConfigSourceList.model_validate(
        {
            "data": [{"order": 1, "source": data, "name": "inner"}],
            "name": "nested",
        },
    )
    logger.debug(f"inner config sourc list: {csl0!r}")
    cs = ConfigSource.model_validate({"order": 2, "source": csl0})
    logger.debug(f"config_source={cs!r}")
    assert cs.order == 2
    assert cs.source == csl0
    assert cs.format == "config_source_list"
    assert cs.enabled
    assert cs.enable_if is None
    assert not cs.is_file()
    assert cs.load() == data
    cs.dump({"updated": True})
    assert cs.source == {"updated": True}
    assert cs.name == "nested"


def test_config_source_list():
    with tempfile.TemporaryDirectory() as tmp:
        f0 = Path(tmp) / "a.yaml"
        with f0.open("w") as fo:
            fo.write(_yaml_content)
        cl = ConfigSourceList.model_validate(
            [
                {
                    "order": 1,
                    "source": {
                        "a": "updated",
                        "e": {1: "updated", "+": {"new": "newvalue"}},
                    },
                },
                {"order": 0, "source": f0, "name": "f0"},
            ],
        )
        logger.debug(f"cl:\n{cl}")
        assert cl[0].name == "f0"
        assert cl[0].order == 0
        assert cl[1].name is None
        assert cl[1].order == 1
        data = cl.load()
        assert data == {
            "a": "updated",
            "c": {"d": 1},
            "e": [0, "updated", {"new": "newvalue"}],
        }


def test_config_source_list_enable_if():
    enabled_if_str = "flag == 2"
    with tempfile.TemporaryDirectory() as tmp:
        f0 = Path(tmp) / "a.yaml"
        with f0.open("w") as fo:
            fo.write(_yaml_content)
        cl = ConfigSourceList.model_validate(
            [
                {
                    "order": 1,
                    "source": {
                        "a": "updated",
                        "e": {1: "updated", "+": {"new": "newvalue"}},
                    },
                    "enable_if": enabled_if_str,
                },
                {"order": 0, "source": f0, "name": "f0"},
            ],
        )
        logger.debug(f"cl:\n{cl}")
        assert cl[0].name == "f0"
        assert cl[0].order == 0
        assert cl[1].name is None
        assert cl[1].order == 1
        assert cl[1].enable_if == enabled_if_str
        data = cl.load()
        assert data == {
            "a": "b",
            "c": {"d": 1},
            "e": [0, True],
        }

        data = cl.load(context={"flag": 2})
        assert data == {
            "a": "updated",
            "c": {"d": 1},
            "e": [0, "updated", {"new": "newvalue"}],
        }

        data = cl.load(context={"flag": 3})
        assert data == {
            "a": "b",
            "c": {"d": 1},
            "e": [0, True],
        }
