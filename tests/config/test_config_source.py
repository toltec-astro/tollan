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
        with open(f0, "w") as fo:
            fo.write(_yaml_content)
        with open(f1, "w") as fo:
            fo.write(_yaml_content)
        assert r.identify_format("read", dict, f0, None, (), {})
        logger.debug(f"yaml_content: {r.read(dict, f0)}")
        assert r.read(dict, f0) == _yaml_content_dict
        assert not r.identify_format("read", dict, f1, None, (), {})
        with pytest.raises(IORegistryError):
            assert r.read(dict, f1) == _yaml_content_dict
        assert r.read(dict, f1, format="yaml") == _yaml_content_dict


def test_config_source_file():
    with tempfile.TemporaryDirectory() as tmp:
        f0 = Path(tmp) / "a.yaml"
        with open(f0, "w") as fo:
            fo.write(_yaml_content)
        cs = ConfigSource.parse_obj({"order": 1, "source": f0, "name": "f0"})
        logger.debug(f"cs:\n{cs}")
        assert cs.order == 1
        assert cs.source == f0.resolve()
        assert cs.format == "yaml"
        assert cs.enabled
        assert cs.enable_if
        assert cs.is_file()
        assert cs.load() == _yaml_content_dict
        f1 = Path(tmp) / "b.yaml"
        cs.dump({"updated": True})
        with open(f0, "r") as fo:
            logger.debug(f"file content:\n{fo.read()}")
        assert cs.load() == {"updated": True}
        assert cs.name == "f0"


def test_config_source_pyobj():
    data = {"in_memory": True}
    cs = ConfigSource.parse_obj({"order": 1, "source": data})
    logger.debug(f"cs:\n{cs}")
    assert cs.order == 1
    assert cs.source == data
    assert cs.format == "pyobj"
    assert cs.enabled
    assert cs.enable_if
    assert not cs.is_file()
    assert cs.load() == data
    cs.dump({"updated": True})
    assert cs.source == {"updated": True}
    assert cs.name == "pyobj"


def test_config_source_list():
    with tempfile.TemporaryDirectory() as tmp:
        f0 = Path(tmp) / "a.yaml"
        with open(f0, "w") as fo:
            fo.write(_yaml_content)
        cl = ConfigSourceList.parse_obj(
            [
                {
                    "order": 1,
                    "source": {
                        "a": "updated",
                        "e": {1: "updated", "+": {"new": "newvalue"}},
                    },
                },
                {"order": 0, "source": f0, "name": "f0"},
            ]
        )
        logger.debug(f"cl:\n{cl}")
        assert cl[0].name == "f0"
        assert cl[0].order == 0
        assert cl[1].name == "pyobj"
        assert cl[1].order == 1
        data = cl.load()
        assert data == {
            "a": "updated",
            "c": {"d": 1},
            "e": [0, "updated", {"new": "newvalue"}],
        }
