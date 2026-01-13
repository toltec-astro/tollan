"""
YAML utilities for tollan.

This module provides custom YAML dumpers and loaders with support for
astronomy-specific types (Time, Quantity, SkyCoord).

Examples
--------
>>> from tollan.utils.yaml import yaml_dump
>>> from astropy.time import Time
>>> from astropy import units as u
>>> data = {'time': Time('2020-01-01'), 'length': 5.0 * u.m}
>>> yaml_str = yaml_dump(data)
>>> print(yaml_str)
length: 5.0 m
time: '2020-01-01T00:00:00.000'
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, overload

import astropy.units as u
import numpy as np
import yaml
from astropy.coordinates import BaseCoordinateFrame
from astropy.time import Time
from yaml.dumper import SafeDumper

if TYPE_CHECKING:
    from io import TextIOBase

    from yaml.nodes import Node, ScalarNode

__all__ = [
    "YamlDumper",
    "add_numpy_scalar_representers",
    "yaml_dump",
    "yaml_load",
    "yaml_loads",
]


class YamlDumper(SafeDumper):
    """
    YAML dumper with support for astronomy types and common scientific objects.

    This dumper extends PyYAML's SafeDumper to handle:

    - Astropy Time objects (serialized as ISO-8601 strings)
    - Astropy Quantity objects (serialized as strings with units, only scalar supported)
    - Coordinate frames (serialized as frame names)
    - Path-like objects (serialized as strings)
    - Enums (serialized as strings)
    - NumPy numeric types (as native Python types)
    - Dataclasses (serialized as dicts)

    Raises
    ------
    ValueError
        If a non-scalar Quantity or Time is encountered.
    """

    def represent_data(self, data: object) -> Node:
        """
        Represent data for YAML serialization, handling astronomy and scientific types.

        Parameters
        ----------
        data : object
            The data to represent.

        Returns
        -------
        Node
            YAML node representation.
        """
        if isinstance(data, BaseCoordinateFrame):
            return self.represent_data(data.name)

        if is_dataclass(data) and not isinstance(data, type):
            return self.represent_data(asdict(data))
        return super().represent_data(data)

    _str_block_style_min_length: int = 100
    """Minimum length of str to format as block."""

    @classmethod
    def _should_use_block(cls, value: str) -> bool:
        """
        Determine if a string should be represented in block style.

        Parameters
        ----------
        value : str
            The string to check.

        Returns
        -------
        bool
            True if block style should be used, otherwise False.
        """
        return "\n" in value or len(value) > cls._str_block_style_min_length

    def represent_scalar(
        self,
        tag: str,
        value: str,
        style: str | None = None,
    ) -> ScalarNode:
        """
        Represent a scalar value, using block style for long or multiline strings.

        Parameters
        ----------
        tag : str
            YAML tag.
        value : str
            Scalar value.
        style : str, optional
            YAML style indicator. If None, block style is used for
            long/multiline strings.

        Returns
        -------
        ScalarNode
            Scalar node for YAML output.
        """
        if style is None:
            style = "|" if self._should_use_block(value) else self.default_style
        return super().represent_scalar(tag=tag, value=value, style=style)

    def ignore_aliases(self, data: object) -> bool:
        """
        Avoid generating YAML aliases (anchors).

        Parameters
        ----------
        data : object
            The data object (unused)

        Returns
        -------
        bool
            Always True
        """
        return True


def _scalar_quantity_representer(dumper: YamlDumper, q: u.Quantity) -> ScalarNode:
    """
    Represent a scalar astropy Quantity as a string with units.

    Parameters
    ----------
    dumper : YamlDumper
        The YAML dumper instance.
    q : astropy.units.Quantity
        The quantity to represent. Must be scalar.

    Returns
    -------
    ScalarNode
        YAML scalar node with string representation.

    Raises
    ------
    ValueError
        If the quantity is not scalar.
    """
    if q.shape != ():
        msg = f"Quantity is not scalar: {q}"
        raise ValueError(msg)
    return dumper.represent_str(q.to_string())


def _scalar_astropy_time_representer(dumper: YamlDumper, t: Time) -> ScalarNode:
    """
    Represent a scalar astropy Time as an ISO-8601 string.

    Parameters
    ----------
    dumper : YamlDumper
        The YAML dumper instance.
    t : astropy.time.Time
        The time to represent. Must be scalar.

    Returns
    -------
    ScalarNode
        YAML scalar node with ISO-8601 string.

    Raises
    ------
    ValueError
        If the time is not scalar.
    """
    if not isinstance(t.isot, str):
        msg = f"Time is not scalar: {t}"
        raise ValueError(msg)  # noqa: TRY004
    return dumper.represent_str(t.isot)


def _path_representer(dumper: YamlDumper, p: Path) -> ScalarNode:
    return dumper.represent_str(str(p))


def _enum_representer(dumper: YamlDumper, p: Enum) -> ScalarNode:
    return dumper.represent_str(str(p))


YamlDumper.add_multi_representer(u.Quantity, _scalar_quantity_representer)
YamlDumper.add_multi_representer(Time, _scalar_astropy_time_representer)
YamlDumper.add_multi_representer(Path, _path_representer)
YamlDumper.add_multi_representer(Enum, _enum_representer)


# from astropy: https://github.com/astropy/astropy/blob/main/astropy/io/misc/yaml.py
def add_numpy_scalar_representers(dumper_cls: type[SafeDumper]) -> None:
    """Add representers for numpy types to the given dumper class."""
    dumper_cls.add_representer(np.bool_, lambda s, d: s.represent_bool(d.item()))
    dumper_cls.add_representer(np.str_, lambda s, d: s.represent_str(d.item()))
    for np_type in [
        np.intc,
        np.intp,
        np.int8,
        np.int16,
        np.int32,
        np.int64,
        np.uint8,
        np.uint16,
        np.uint32,
        np.uint64,
    ]:
        dumper_cls.add_representer(
            np_type,
            lambda s, d: s.represent_int(d.item()),
        )
    for np_type in [np.float16, np.float32, np.float64, np.longdouble]:
        dumper_cls.add_representer(np_type, lambda s, d: s.represent_float(d.item()))


add_numpy_scalar_representers(YamlDumper)


@overload
def yaml_dump(data: object, output: None = None, **kwargs: object) -> str: ...


@overload
def yaml_dump(
    data: object,
    output: str | os.PathLike | TextIOBase,
    **kwargs: object,
) -> None: ...


def yaml_dump(
    data: object,
    output: str | os.PathLike[str] | TextIOBase | None = None,
    **kwargs: object,
) -> None | str:
    """
    Serialize data as YAML and write to a file, stream, or return as string.

    Parameters
    ----------
    data : object
        The data to serialize.
    output : str or os.PathLike or TextIOBase or None, optional
        Output destination:
        - None: return YAML as string
        - str or PathLike: write to file
        - TextIOBase: write to stream
    **kwargs
        Additional keyword arguments passed to `yaml.dump`.

    Returns
    -------
    str or None
        YAML string if output is None, otherwise None.

    Raises
    ------
    TypeError
        If output is not a valid type.
    """
    if isinstance(output, (str, os.PathLike)):
        ctx = Path(output).open("w")  # noqa: SIM115 # ty: ignore[invalid-argument-type]
    elif output is None or hasattr(output, "write"):
        ctx = contextlib.nullcontext(output)
    else:
        msg = "output has to be str, PathLike, TextIO, or None."
        raise TypeError(msg)
    with ctx as stream:
        return yaml.dump(data, stream, Dumper=YamlDumper, **kwargs)  # pyright: ignore[reportArgumentType, reportCallIssue]


def yaml_load(source: str | os.PathLike | TextIOBase) -> object:
    """
    Load YAML data from a file, stream, or string.

    Parameters
    ----------
    source : str or os.PathLike or TextIOBase
        The YAML source. Can be:
        - File path: read from file
        - File object: read from stream
        - String: parse as YAML

    Returns
    -------
    object
        Parsed YAML data.

    Raises
    ------
    TypeError
        If source is not a valid type.
    """
    # Handle file objects
    if hasattr(source, "read"):
        return yaml_loads(source)  # type: ignore[arg-type]

    def _read_filepath(p: os.PathLike) -> object:
        with Path(p).open() as fo:
            return yaml_loads(fo)

    # Try as file path if it's a Path or looks like a file
    if isinstance(source, os.PathLike):
        return _read_filepath(source)

    # For strings, check if it's a file that exists
    if isinstance(source, str):
        try:
            path = Path(source)
            if path.exists() and path.is_file():
                return _read_filepath(path)
        except (OSError, ValueError):
            pass
        # Not a valid path, treat as YAML string
        return yaml_loads(source)
    msg = "source has to be PathLike, TextIO, or str."
    raise TypeError(msg)


def yaml_loads(stream: str | TextIOBase) -> object:
    """
    Load YAML data from a string or stream.

    Parameters
    ----------
    stream : str or TextIOBase
        YAML string or stream to parse.

    Returns
    -------
    object
        Parsed YAML data.
    """
    return yaml.safe_load(stream)
