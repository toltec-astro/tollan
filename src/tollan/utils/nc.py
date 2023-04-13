import textwrap
from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
from tabulate import tabulate

from .fileloc import FileLoc
from .log import logged_closing, logger

__all__ = ["ncopen", "ncinfo", "NcNodeMapper"]


def _ncstr(var):
    def _make_str(s):
        try:
            stop = s.index(None)
        except ValueError:
            stop = None
        s = s[:stop]
        s = [c.decode("utf-8") for c in s]
        return "".join(s).strip()

    s = var[:].tolist()
    if len(var.shape) == 1:
        return _make_str(s)
    # TODO make this work for ndim > 2
    if len(var.shape) == 2:  # noqa: PLR2004
        return [_make_str(ss) for ss in s]
    raise RuntimeError("var has to be 2-d or less")


def ncstr(var):
    """Return str from nc variable."""
    if var.dtype != "|S1":
        raise RuntimeError("var is not a string.")
    return _ncstr(var)


def ncopen(source, **kwargs) -> Any:
    """Return a context manager to open netCDF file.

    Parameters
    ----------
    source : str, `~pathlib.Path`, `netCDF4.Dataset`
        The file path to open. No-op for opened dataset.
    """
    if isinstance(source, netCDF4.Dataset):  # type: ignore
        if source.isopen():
            return nullcontext(source)
        raise RuntimeError("dataset is closed.")
    dataset = netCDF4.Dataset(str(source), **kwargs)  # type: ignore
    return logged_closing(logger.debug, dataset, msg=f"close {dataset.filepath()}")


def ncinfo(source):
    """Return a pretty formatted string for netCDF4 dataset."""

    def fmt_var(var):
        if not var.dimensions or (var.dtype == "|S1" and len(var.dimensions) == 1):
            v = var[:]
            try:
                if var.dtype == "|S1":
                    return ncstr(var)
            except ValueError:
                return v
            else:
                return f"{v:g}"
        return "[{}]".format(", ".join(d for d in var.dimensions))

    def fmt_items(items, headers, indent):
        return textwrap.indent(tabulate(items, headers=headers), prefix=" " * indent)

    with ncopen(source) as nc:
        attnames = [(name, nc.getncattr(name)) for name in nc.ncattrs()]
        dimnames = [
            f"{dimname}({len(nc.dimensions[dimname])})" for dimname in nc.dimensions
        ]
        varnames = [
            (
                varname,
                fmt_var(nc.variables[varname]),
                nc.variables[varname].dtype,
                getattr(nc.variables[varname], "long_name", None),
            )
            for varname in nc.variables
        ]
        grpnames = [(grpname,) for grpname in nc.groups]

        if nc.path == "/":
            head = "{0.path}: [{0.data_model}, {0.disk_format}]".format(nc)
        else:
            head = f"{nc.path}:"
        items_indent = 10
        return """{{
    file: {}
    {head}
      atts:\n{atts}
      dims:\n{dims}
      vars:\n{vars_}
      grps:\n{grps}
}}""".format(
            nc.filepath(),
            head=head,
            atts=fmt_items(attnames, headers=["name", "value"], indent=items_indent),
            dims="\n".join(
                textwrap.wrap(
                    ", ".join(dimnames),
                    width=60,
                    initial_indent=" " * items_indent,
                    subsequent_indent=" " * items_indent,
                ),
            ),
            vars_=fmt_items(
                varnames,
                headers=["name", "info", "dtype", "description"],
                indent=items_indent,
            ),
            grps=fmt_items(grpnames, headers=["name"], indent=items_indent),
        )


class NcNodeMapperError(RuntimeError):
    """Raise when failed accessing data through `NcNodeMapperMixin`."""


class NcNodeMapperMixin:
    """A mix-in class that help access netCDF4 datasets with mapped names.

    The cooperating class is shall provide implementation of :attr:`_nc_node`,
    and `_nc_node_map`.

    """

    _nc_node: Any
    _nc_node_map: Any

    @property
    def nc_node(self):
        """The mapped netCDF data node.

        This could be a netCDF dataset or group.
        """
        if hasattr(self, "_nc_node") and self._nc_node.isopen():
            return self._nc_node
        raise NcNodeMapperError("no netCDF dataset.")

    @property
    def nc_node_map(self):
        """The dict specifies variable name mapping."""
        return self._nc_node_map

    def __getitem__(self, k):
        """Return the mapped variable name for `k`.

        `k` is returned if it is not present in the map.
        """
        name = self.nc_node_map.get(k, k)
        if isinstance(name, (tuple, list)):
            # check the first available name in the node
            for n in name:
                if self.has_key(n):
                    return n
            return k
        return name

    def has_var(self, *ks):
        """Return True if all keys in `ks` are present in the node variables."""
        return all(self[k] in self.nc_node.variables for k in ks)

    def has_dim(self, *ks):
        """Return True if all keys in `ks` are present in the node dimensions."""
        return all(self[k] in self.nc_node.dimensions for k in ks)

    def has_key(self, *ks):
        """Return True if all keys in `ks` are present in the node."""
        return all(
            (
                (self[k] in self.nc_node.variables)
                or (self[k] in self.nc_node.dimensions)
            )
            for k in ks
        )

    def get_var(self, k):
        """Return the variable mapped by `k`."""
        return self.nc_node.variables[self[k]]

    def get_dim(self, k):
        """Return the dimension mapped by `k`."""
        return self.nc_node.dimensions[self[k]].size

    def get_scalar(self, k):
        """Return the scalar value mapped by `k`."""
        v = self.get_var(k)
        if v.shape == ():
            return v[:].item()
        raise NcNodeMapperError(f"variable {k} -> {self[k]} is not a scalar.")

    def get_str(self, k):
        """Retrun the string value mapped by `k`."""
        return ncstr(self.get_var(k))

    def get_value(self, k):
        """Try return the value mapped by `k`.

        It first tries the variables then the dimensions. It also checks the
        shape and type of the variable for scalar or string. Otherwise it
        returns the variable instance.
        """
        if self.has_var(k):
            v = self.get_var(k)
            if v.shape == ():
                return v[:].item()
            if v.dtype == "|S1":
                if len(v.shape) == 1:
                    # single string
                    return _ncstr(v)
                # a list of strings
                # TODO implement this if needed.
                return v
            # large data blob
            return v
        # dim
        return self.get_dim(k)

    def info(self):
        """Return the nc info pretty formatted."""
        return ncinfo(self.nc_node)

    def set_str(self, k, s, dim=128, exist_ok=False):
        """Set the string to variable mapped by `k`."""
        name = self[k]
        nc = self.nc_node
        if name in nc.variables:
            if not exist_ok:
                raise ValueError(f"variable key={k} name={name} exists.")
            v = nc.variables[name]
            # check d type and dimension
            if not v.dtype.startswith("|S"):
                raise ValueError(f"variable key={k} name={name} is not of str type.")
            v_dim = self.get_dim(v.dimensions[0])
            if v_dim < len(s):
                raise ValueError(
                    f"variable key={k} name={name} is too short to hold the string.",
                )
        else:
            if not isinstance(dim, str) or dim is None:
                if dim is None:
                    dim = len(s)
                dim_name = f"{name}_slen"
                nc.createDimension(dim_name, dim)
            else:
                dim_name = dim
            v = nc.createVariable(name, "S1", (dim_name,))
        v[:] = netCDF4.stringtochar(np.array([s], dtype=f"S{dim}"))  # type: ignore
        return v

    def set_scalar(self, k, s, dtype=None, exist_ok=False):
        """Set the scalar value to variable mapped by `k`."""
        name = self[k]
        nc = self.nc_node
        if dtype is None:
            dt = np.dtype(type(s))
            dtype = f"{dt.kind}{dt.itemsize}"
        if name in nc.variables:
            if not exist_ok:
                raise ValueError(f"variable key={k} name={name} exists.")
            v = nc.variables[name]
            if v.dtype != dtype:
                raise ValueError(
                    f"variable key={k} name={name} has wrong dtype {dtype}.",
                )
        else:
            v = nc.createVariable(name, dtype, ())
        v[:] = s
        return v

    def update(self, d):
        """Add mappings specified by `d`."""
        for k, v in d.items():
            if isinstance(v, str):
                self._nc_node_map[k] = v
            else:
                # variable
                self._nc_node_map[k] = v.name


class NcNodeMapper(ExitStack, NcNodeMapperMixin):
    """A adaptor class that accesses netCDF4 dataset with a custom name map.

    Parameters
    ----------
    source : str, `pathlib.Path`, `FileLoc`, `netCDF4.Dataset`
        The netCDF file location or netCDF dataset.
    """

    def __init__(self, nc_node_map=None, source=None, **kwargs):
        self._nc_node_map = nc_node_map or {}
        super().__init__()
        # open the data source if specified.
        if source is not None:
            self.open(source, **kwargs)

    def open(self, source, **kwargs):
        """Return a context to operate on data `source`.

        Parameters
        ----------
        source : str, `pathlib.Path`, `FileLoc`, `netCDF4.Dataset`
            The netCDF file location or netCDF dataset.

        **kwargs :
            The keyword arguments passed to `netCDF4.Dataset` constructor.
        """
        if isinstance(source, FileLoc):
            if not source.is_local:
                raise ValueError("source should point to a local file.")
            source = source.path
        elif isinstance(source, (Path, str)):
            pass
        else:
            # netCDF dataset
            pass
        self._nc_node = self.enter_context(ncopen(source, **kwargs))
        return self

    def __exit__(self, *args):
        super().__exit__(*args)
        # reset the nc_node so that this object can be pickled if
        # not bind to open dataset.
        del self._nc_node

    def set_nc_node(self, nc_node):
        """Set the node to map.

        This assumes the `nc_node` is an externally opened dataset.
        """
        self._nc_node = nc_node

    @property
    def fileloc(self):
        """The opened file."""
        return FileLoc(self.nc_node.filepath())

    def sync(self):
        """Sync the underlying file."""
        return self.nc_node.sync()
