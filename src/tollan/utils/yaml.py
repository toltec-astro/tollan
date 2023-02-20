#!/usr/bin/env python

import os
from io import IOBase, StringIO
from pathlib import PosixPath

import astropy.units as u
import yaml
from astropy.coordinates import BaseCoordinateFrame
from astropy.time import Time
from yaml.dumper import SafeDumper

from .general import ensure_readable_fileobj


class YamlDumper(SafeDumper):
    """Yaml dumper that handles common types."""

    def represent_data(self, data):
        if isinstance(data, BaseCoordinateFrame):
            return self.represent_data(data.name)
        return super().represent_data(data)


def _quantity_representer(dumper, q):
    return dumper.represent_str(q.to_string())


def _astropy_time_representer(dumper, t):
    return dumper.represent_str(t.isot)


def _path_representer(dumper, p):
    return dumper.represent_str(p.as_posix())


def _should_use_block(value):
    return "\n" in value or len(value) > 100


def _represent_scalar(self, tag, value, style=None):
    if style is None:
        if _should_use_block(value):
            style = "|"
        else:
            style = self.default_style

    node = yaml.representer.ScalarNode(tag, value, style=style)
    if self.alias_key is not None:
        self.represented_objects[self.alias_key] = node
    return node


YamlDumper.represent_scalar = _represent_scalar
YamlDumper.add_multi_representer(u.Quantity, _quantity_representer)
YamlDumper.add_multi_representer(Time, _astropy_time_representer)
YamlDumper.add_multi_representer(PosixPath, _path_representer)


def yaml_dump(data, output=None, **kwargs):
    """Dump `data` as YAML to `output`

    Parameters
    ----------
    data : dict
        The data to write.
    output : io.StringIO, optional
        The object to write to. If None, return the YAML as string.
    """
    _output = output  # save the original output to check for None
    if output is None:
        output = StringIO()
    ctx = None
    if isinstance(output, (str, os.PathLike)):
        ctx = open(output, "w")
        output = ctx.__enter__()
    if not isinstance(output, IOBase):
        raise ValueError("output has to be stream object.")
    yaml.dump(data, output, Dumper=YamlDumper, **kwargs)
    if ctx is not None:
        ctx.close()
    if _output is None:
        return output.getvalue()
    return None


def yaml_load(source):
    with ensure_readable_fileobj(source) as fo:
        return yaml.safe_load(fo)
