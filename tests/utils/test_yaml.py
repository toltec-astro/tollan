"""Tests for tollan.utils.yaml module."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pytest
import yaml
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from tollan.utils.yaml import (
    add_numpy_scalar_representers,
    yaml_dump,
    yaml_load,
    yaml_loads,
)


class Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass
class SimpleData:
    name: str
    value: int


class TestYamlDumper:
    """Test YamlDumper class functionality."""

    def test_basic_types(self):
        """Test basic Python types."""
        data = {"string": "hello", "int": 42, "float": 3.14, "bool": True}
        result = yaml_dump(data)
        loaded = yaml_loads(result)
        assert loaded == data

    def test_astropy_time_scalar(self):
        """Test serialization of scalar Time object."""
        data = {"time": Time("2020-01-01T00:00:00")}
        result = yaml_dump(data)
        assert "2020-01-01T00:00:00" in result
        # Parse back
        loaded = yaml_loads(result)
        assert loaded["time"] == "2020-01-01T00:00:00.000"  # type: ignore[index]

    def test_astropy_time_non_scalar_raises(self):
        """Test that non-scalar Time raises ValueError."""
        data = {"time": Time(["2020-01-01", "2020-01-02"])}
        with pytest.raises(ValueError, match="Time is not scalar"):
            yaml_dump(data)

    def test_quantity_scalar(self):
        """Test serialization of scalar Quantity."""
        data = {"length": 5.0 * u.m}
        result = yaml_dump(data)
        assert "5.0 m" in result

    def test_quantity_non_scalar_raises(self):
        """Test that non-scalar Quantity raises ValueError."""
        data = {"lengths": [1.0, 2.0] * u.m}
        with pytest.raises(ValueError, match="Quantity is not scalar"):
            yaml_dump(data)

    def test_path_like(self):
        """Test serialization of Path-like objects."""
        data = {"path": Path("/some/path")}
        result = yaml_dump(data)
        assert "/some/path" in result

    def test_enum(self):
        """Test serialization of Enum."""
        data = {"color": Color.RED}
        result = yaml_dump(data)
        assert "Color.RED" in result

    def test_dataclass(self):
        """Test serialization of dataclass."""
        data = {"obj": SimpleData(name="test", value=42)}
        result = yaml_dump(data)
        loaded = yaml_loads(result)
        assert loaded == {"obj": {"name": "test", "value": 42}}

    def test_coordinate_frame(self):
        """Test serialization of coordinate frames."""
        coord = SkyCoord(ra=10.0 * u.deg, dec=20.0 * u.deg, frame="icrs")
        data = {"frame": coord.frame}
        result = yaml_dump(data)
        assert "icrs" in result

    def test_long_string_block_style(self):
        """Test that long strings use block style."""
        long_string = "x" * 200
        data = {"long": long_string}
        result = yaml_dump(data)
        # Block style uses |
        assert "long: |" in result

    def test_multiline_string_block_style(self):
        """Test that multiline strings use block style."""
        multiline = "line1\nline2\nline3"
        data = {"text": multiline}
        result = yaml_dump(data)
        assert "text: |" in result

    def test_no_aliases(self):
        """Test that aliases (anchors) are not generated."""
        shared_obj = {"shared": "value"}
        data = {"a": shared_obj, "b": shared_obj}
        result = yaml_dump(data)
        # Should not contain anchor/alias markers
        assert "*" not in result
        assert "&" not in result


class TestNumpyScalarRepresenters:
    """Test numpy scalar type representers."""

    def test_numpy_bool(self):
        """Test numpy bool types."""
        data = {"value": np.bool_(True)}  # noqa: FBT003
        result = yaml_dump(data)
        loaded = yaml_loads(result)
        assert loaded["value"] is True  # type: ignore[index]

    def test_numpy_int_types(self):
        """Test various numpy int types."""
        int_types = [
            np.int8(1),
            np.int16(2),
            np.int32(3),
            np.int64(4),
            np.uint8(5),
            np.uint16(6),
            np.uint32(7),
            np.uint64(8),
        ]
        for i, value in enumerate(int_types):
            data = {"value": value}
            result = yaml_dump(data)
            loaded = yaml_loads(result)
            assert loaded["value"] == i + 1  # type: ignore[index]

    def test_numpy_float_types(self):
        """Test various numpy float types."""
        float_types = [np.float16(1.5), np.float32(2.5), np.float64(3.5)]
        for i, value in enumerate(float_types):
            data = {"value": value}
            result = yaml_dump(data)
            loaded = yaml_loads(result)
            assert abs(loaded["value"] - (i + 1.5)) < 0.01  # type: ignore[index]

    def test_numpy_str(self):
        """Test numpy string type."""
        data = {"value": np.str_("hello")}
        result = yaml_dump(data)
        loaded = yaml_loads(result)
        assert loaded["value"] == "hello"  # type: ignore[index]

    def test_add_representers_to_custom_dumper(self):
        """Test adding numpy representers to custom dumper."""
        from yaml.dumper import SafeDumper

        class CustomDumper(SafeDumper):
            pass

        add_numpy_scalar_representers(CustomDumper)
        data = {"value": np.int32(42)}
        result = yaml.dump(data, Dumper=CustomDumper)
        loaded = yaml_loads(result)
        assert loaded["value"] == 42  # type: ignore[index]


class TestYamlDump:
    """Test yaml_dump function."""

    def test_dump_to_string(self):
        """Test dumping to string (default)."""
        data = {"key": "value"}
        result = yaml_dump(data)
        assert isinstance(result, str)
        assert "key: value" in result

    def test_dump_to_file_path_string(self):
        """Test dumping to file using string path."""
        data = {"key": "value"}
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.yaml"
            result = yaml_dump(data, output=str(filepath))
            assert result is None
            assert filepath.exists()
            with filepath.open() as f:
                loaded = yaml_loads(f)
            assert loaded == data

    def test_dump_to_file_path_object(self):
        """Test dumping to file using Path object."""
        data = {"key": "value"}
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.yaml"
            result = yaml_dump(data, output=filepath)
            assert result is None
            assert filepath.exists()
            loaded = yaml_load(filepath)
            assert loaded == data

    def test_dump_to_stream(self):
        """Test dumping to file stream."""
        data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            result = yaml_dump(data, output=f)  # type: ignore[arg-type]
            assert result is None
            temp_path = f.name
        try:
            loaded = yaml_load(temp_path)
            assert loaded == data
        finally:
            Path(temp_path).unlink()

    def test_dump_invalid_output_type(self):
        """Test that invalid output type raises TypeError."""
        data = {"key": "value"}
        with pytest.raises(
            TypeError,
            match="output has to be str, PathLike, TextIO, or None",
        ):
            yaml_dump(data, output=123)  # type: ignore[no-matching-overload]

    def test_dump_with_kwargs(self):
        """Test passing additional kwargs to yaml.dump."""
        data = {"key": "value"}
        result = yaml_dump(data, default_flow_style=True)
        # Flow style should have curly braces
        assert "{" in result


class TestYamlLoad:
    """Test yaml_load function."""

    def test_load_from_string(self):
        """Test loading from YAML string."""
        yaml_str = "key: value\nnum: 42"
        result = yaml_load(yaml_str)
        assert result == {"key": "value", "num": 42}

    def test_load_from_file_path_string(self):
        """Test loading from file using string path."""
        data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name
        try:
            result = yaml_load(temp_path)
            assert result == data
        finally:
            Path(temp_path).unlink()

    def test_load_from_file_path_object(self):
        """Test loading from file using Path object."""
        data = {"key": "value"}
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.yaml"
            with filepath.open("w") as f:
                yaml.dump(data, f)
            result = yaml_load(filepath)
            assert result == data

    def test_load_from_stream(self):
        """Test loading from file stream."""
        data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name
        try:
            with Path(temp_path).open() as f:
                result = yaml_load(f)
            assert result == data
        finally:
            Path(temp_path).unlink()

    def test_load_nonexistent_file_as_yaml_string(self):
        """Test that nonexistent file path is treated as YAML string."""
        yaml_str = "key: value"
        result = yaml_load(yaml_str)
        assert result == {"key": "value"}


class TestYamlLoads:
    """Test yaml_loads function."""

    def test_loads_from_string(self):
        """Test loading from YAML string."""
        yaml_str = "key: value\nnum: 42"
        result = yaml_loads(yaml_str)
        assert result == {"key": "value", "num": 42}

    def test_loads_from_stream(self):
        """Test loading from stream."""
        data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name
        try:
            with Path(temp_path).open() as f:
                result = yaml_loads(f)
            assert result == data
        finally:
            Path(temp_path).unlink()


class TestRoundTrip:
    """Test round-trip serialization and deserialization."""

    def test_complex_nested_structure(self):
        """Test round-trip with complex nested data."""
        data = {
            "metadata": {"name": "test", "version": 1},
            "values": [1, 2, 3],
            "nested": {"a": {"b": {"c": "deep"}}},
        }
        yaml_str = yaml_dump(data)
        loaded = yaml_loads(yaml_str)
        assert loaded == data

    def test_mixed_types(self):
        """Test round-trip with mixed types."""
        data = {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }
        yaml_str = yaml_dump(data)
        loaded = yaml_loads(yaml_str)
        assert loaded == data
