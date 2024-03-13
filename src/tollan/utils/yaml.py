import os
from enum import Enum
from io import IOBase, StringIO
from pathlib import Path, PosixPath

import astropy.units as u
import yaml
from astropy.coordinates import BaseCoordinateFrame
from astropy.time import Time
from yaml.dumper import SafeDumper

from .fileloc import FileLoc
from .general import ensure_readable_fileobj

__all__ = ["YamlDumper", "yaml_dump", "yaml_load", "yaml_loads"]


class YamlDumper(SafeDumper):
    """Yaml dumper that handles common types."""

    def represent_data(self, data):
        """Represent data handling skycoords."""
        if isinstance(data, BaseCoordinateFrame):
            return self.represent_data(data.name)
        return super().represent_data(data)

    _str_block_style_min_length = 100
    """Mininum length of str to format as block."""

    @classmethod
    def _should_use_block(cls, value):
        return "\n" in value or len(value) > cls._str_block_style_min_length

    def represent_scalar(self, tag, value, style=None):
        """Represent scalar with better block logic."""
        if style is None:
            style = "|" if self._should_use_block(value) else self.default_style
        return super().represent_scalar(tag=tag, value=value, style=style)


def _quantity_representer(dumper, q):
    return dumper.represent_str(q.to_string())


def _astropy_time_representer(dumper, t):
    return dumper.represent_str(t.isot)


def _path_representer(dumper, p):
    return dumper.represent_str(str(p))


def _enum_representer(dumper, p):
    return dumper.represent_str(str(p))


def _fileloc_representer(dumper, p):
    return dumper.represent_str(p.as_rsync())


YamlDumper.add_multi_representer(u.Quantity, _quantity_representer)
YamlDumper.add_multi_representer(Time, _astropy_time_representer)
YamlDumper.add_multi_representer(PosixPath, _path_representer)
YamlDumper.add_multi_representer(Enum, _enum_representer)
YamlDumper.add_multi_representer(FileLoc, _fileloc_representer)


def yaml_dump(data, output=None, **kwargs):
    """Dump `data` as YAML to `output`.

    Parameters
    ----------
    data : dict
        The data to write.
    output : io.StringIO, optional
        The object to write to. If None, return the YAML as string.
    """
    out = StringIO() if output is None else output
    ctx = None
    if isinstance(out, str | os.PathLike):
        ctx = Path(out).open("w")  # noqa: SIM115
        out = ctx.__enter__()
    if not isinstance(out, IOBase):
        raise TypeError("output has to be stream object.")
    yaml.dump(data, out, Dumper=YamlDumper, **kwargs)
    if ctx is not None:
        ctx.close()
    if output is None:
        return out.getvalue()  # type: ignore
    return None


def yaml_load(source):
    """Load yaml data.

    `source` can be filepath, stream, or string.
    """
    with ensure_readable_fileobj(source) as fo:
        return yaml_loads(fo)


def yaml_loads(stream):
    """Load yaml data from string or stream."""
    return yaml.safe_load(stream)
