#! /usr/bin/env python
import netCDF4
from ..fmt import pformat_list
from .. import FileLoc, fileloc
from contextlib import ExitStack
from contextlib import nullcontext
from ..log import logged_closing, get_logger
from pathlib import Path
import numpy as np


__all__ = ['ncopen', 'ncinfo', 'NcNodeMapper']


def _ncstr(var):

    def _make_str(s):
        try:
            stop = s.index(None)
        except ValueError:
            stop = None
        s = s[:stop]
        s = [c.decode('utf-8') for c in s]
        return ''.join(s).strip()

    s = var[:].tolist()
    if len(var.shape) == 1:
        return _make_str(s)
    # TODO make this work for ndim > 2
    elif len(var.shape) == 2:
        return [_make_str(ss) for ss in s]
    raise RuntimeError("var has to be 2-d or less")


def ncstr(var):
    """Return str from nc variable."""
    if var.dtype != '|S1':
        raise RuntimeError("var is not a string.")
    return _ncstr(var)


def ncopen(source, **kwargs):
    """Return a context manager to open netCDF file.

    Parameters
    ----------
    source : str, `~pathlib.Path`, `netCDF4.Dataset`
        The file path to open. No-op for opened dataset.
    """
    if isinstance(source, netCDF4.Dataset):
        if source.isopen():
            return nullcontext(source)
        raise RuntimeError("dataset is closed.")
    logger = get_logger()
    dataset = netCDF4.Dataset(str(source), **kwargs)
    return logged_closing(
            logger.debug, dataset, msg=f'close {dataset.filepath()}')


def ncinfo(source):
    """Return a pretty formatted string for netCDF4 dataset."""

    def fmt_var(var):
        if not var.dimensions or (var.dtype == '|S1' and len(
                var.dimensions) == 1):
            v = var[:]
            try:
                if var.dtype == "|S1":
                    return ncstr(var)
                return "{:g}".format(v)
            except ValueError:
                return v
        return "[{}]".format(", ".join(d for d in var.dimensions))

    with ncopen(source) as nc:

        attnames = [
            (name, nc.getncattr(name)) for name in nc.ncattrs()]
        dimnames = [
            (dimname, len(nc.dimensions[dimname]))
            for dimname in nc.dimensions.keys()]
        varnames = [
            (
                varname,
                fmt_var(nc.variables[varname]),
                nc.variables[varname].dtype,
                getattr(nc.variables[varname], "long_name", None),
                )
            for varname in nc.variables.keys()
            ]
        grpnames = [
            (grpname, ) for grpname in nc.groups.keys()]

        if nc.path == '/':
            head = "{0.path}: [{0.data_model}, {0.disk_format}]".format(nc)
        else:
            head = "{}:".format(nc.path)
        info = """{{
      file: {}
      {head}
        atts: {atts}
        dims: {dims}
        vars: {vars_}
        grps: {grps}
      }}""".format(
            nc.filepath(),
            head=head,
            atts=pformat_list(attnames, 6),
            dims=pformat_list(dimnames, 6),
            vars_=pformat_list(varnames, 6),
            grps=pformat_list(grpnames, 6)
            )
    return info


class NcNodeMapperError(RuntimeError):
    """Raise when failed accessing data through `NcNodeMapperMixin`."""
    pass


class NcNodeMapperMixin(object):
    """A mix-in class that help access netCDF4 datasets with mapped names.

    The cooperating class is shall provide implementation of :attr:`_nc_node`,
    and `_nc_node_map`.

    """

    @property
    def nc_node(self):
        """The mapped netCDF data node.

        This could be a netCDF dataset or group.
        """
        if hasattr(self, '_nc_node') and self._nc_node.isopen():
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
                if self.hasname(n):
                    return n
            else:
                return k
        return name

    def hasvar(self, *ks):
        """Return True if all keys in `ks` are present in the node variables.
        """
        return all(
                self[k] in self.nc_node.variables for k in ks)

    def hasdim(self, *ks):
        """Return True if all keys in `ks` are present in the node dimensions.
        """
        return all(
                self[k] in self.nc_node.dimensions for k in ks)

    def hasname(self, *ks):
        """Return True if all keys in `ks` are present in the node."""
        return all(
                (
                    (self[k] in self.nc_node.variables)
                    or (self[k] in self.nc_node.dimensions)
                    )
                for k in ks)

    def getvar(self, k):
        return self.nc_node.variables[self[k]]

    def getdim(self, k):
        return self.nc_node.dimensions[self[k]].size

    def getscalar(self, k):
        v = self.getvar(k)
        if v.shape == ():
            return v[:].item()
        raise NcNodeMapperError(f'variable {k} -> {self[k]} is not a scalar.')

    def getstr(self, k):
        return ncstr(self.getvar(k))

    def getany(self, k):
        """Try return the value of key `k` from the node for simple variables.

        It first tries the variables then the dimensions. It also checks the
        shape and type of the variable for scalar or string. Otherwise it
        returns the variable instance.
        """
        if self.hasvar(k):
            v = self.getvar(k)
            if v.shape == ():
                return v[:].item()
            if v.dtype == '|S1':
                if len(v.shape) == 1:
                    # single string
                    return _ncstr(v)
                # a list of strings
                # TODO implement this if needed.
                return v
            # large data blob
            return v
        # dim
        return self.getdim(k)

    def info(self):
        return ncinfo(self.nc_node)

    def setstr(self, k, s, dim=128):
        name = self[k]
        nc = self.nc_node
        if not isinstance(dim, str) or dim is None:
            if dim is None:
                dim = len(s)
            dim_name = f'{name}_slen'
            nc.createDimension(dim_name, dim)
        else:
            dim_name = dim
        v = nc.createVariable(name, 'S1', (dim_name, ))
        v[:] = netCDF4.stringtochar(np.array([s], dtype=f'S{dim}'))
        return v

    def setscalar(self, k, s, dtype=None):
        name = self[k]
        nc = self.nc_node
        if dtype is None:
            dt = np.dtype(type(s))
            dtype = f'{dt.kind}{dt.itemsize}'
        v = nc.createVariable(name, dtype, ())
        v[:] = s
        return v

    def update(self, d):
        """Add mappings specified by `d`."""
        for k, v in d.items():
            if isinstance(v, str):
                self._nc_node_map[k] = v
            else:
                self._nc_node_map[k] = v.name


class NcNodeMapper(ExitStack, NcNodeMapperMixin):
    """A adaptor class that accesses netCDF4 dataset with a custom name map.

    Parameters
    ----------
    source : str, `pathlib.Path`, `FileLoc`, `netCDF4.Dataset`
        The netCDF file location or netCDF dataset.
    """

    logger = get_logger()

    def __init__(self, nc_node_map=None, source=None, **kwargs):
        if nc_node_map is None:
            nc_node_map = dict()  # an empty map also works
        self._nc_node_map = nc_node_map
        super().__init__()
        # open the given source
        if source is not None:
            self.open(source, **kwargs)

    def open(self, source, **kwargs):
        """Return a context to operate on `source`.

        Parameters
        ----------
        source : str, `pathlib.Path`, `FileLoc`, `netCDF4.Dataset`
            The netCDF file location or netCDF dataset.

        **kwargs :
            The keyword arguments passed to `netCDF4.Dataset` constructor.
        """
        if isinstance(source, FileLoc):
            if not source.is_local:
                raise ValueError('source should point to a local file.')
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
    def file_loc(self):
        """The opened file.

        """
        return fileloc(self.nc_node.filepath())

    def sync(self):
        """Sync the underlying file."""
        return self.nc_node.sync()
