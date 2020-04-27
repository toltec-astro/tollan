#! /usr/bin/env python
import netCDF4
import numpy as np
from ..fmt import pformat_list
from ..log import get_logger, logit
import functools


__all__ = ['ncopen', 'ncinfo', 'NcNodeMapper']


def ncstr(var):
    """Return str from nc variable."""
    s = var[:].tolist()
    s = [c.decode('utf-8') for c in s if c is not None]
    return ''.join(s).strip()


def _close(*args, nc=None):
    logger = get_logger()
    with logit(logger.debug, f"close {nc.filepath()}"):
        nc.close()


def ncopen(source):
    """Return an opened netCDF4 dataset a long with a close method."""
    if isinstance(source, netCDF4.Dataset):
        return source, lambda *args: None
    else:
        nc = netCDF4.Dataset(str(source))
        return nc, functools.partial(_close, nc=nc)


def ncinfo(source):
    """Return a pretty formatted string for netCDF4 dataset."""

    nc, close = ncopen(source)

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
    close()
    return info


class NcNodeMapper(object):
    """A adaptor class that accesses netCDF4 dataset with a custom name map."""

    def __init__(self, nc, map_):
        self.nc = nc
        self._ = map_

    def hasvar(self, *ks):
        return all(self[k] in self.nc.variables for k in ks)

    def getvar(self, k):
        return self.nc.variables[self[k]]

    def getdim(self, k):
        return self.nc.dimensions[self[k]].size

    def getscalar(self, k):
        return np.asscalar(self.getvar(k)[:])

    def getstr(self, k):
        return ncstr(self.getvar(k))

    def __getitem__(self, k):
        return self._[k]

    def __contains__(self, k):
        return k in self._

    def get(self, k):
        if self.hasvar(k):
            v = self.getvar(k)
            if not v.dimensions or (v.dtype == '|S1' and len(
                    v.dimensions) == 1):
                v = v[:]
                try:
                    if v.dtype == "|S1":
                        return ncstr(v)
                    return np.asscalar(v)
                except ValueError:
                    return v
            return v
        return self.getdim(k)
