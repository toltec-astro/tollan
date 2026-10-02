"""Conversions between xarray DataArrays, Datasets, and DataTree nodes.

``ensure_dataset`` and ``ensure_datatree`` change the container while sharing
its array storage. ``unwrap_data_source`` selects the DataArray from a Dataset
wrapper created by these helpers. Tree operations use the supplied node.

Examples
--------
Wrap a named array and recover its variable attributes:

>>> import xarray as xr
>>> da = xr.DataArray([1., 2., 3.], dims="sample", name="signal",
...                   attrs={"units": "V"})
>>> ds = ensure_dataset(da)
>>> list(ds.data_vars)
['signal']
>>> ds["signal"].attrs
{'units': 'V'}
>>> unwrap_data_source(ds).identical(da)
True
>>> ds["signal"].data is da.data
True
>>> ensure_dataset(ds) is ds
True

An unnamed array uses ``data`` as its variable name. Unwrapping retains that
assigned name:

>>> unnamed = ensure_dataset(da.rename(None))
>>> unwrap_data_source(unnamed).name
'data'

A Dataset or DataArray becomes the payload at ``/`` when converted to a tree:

>>> dt = ensure_datatree(da)
>>> dt.path, dt.name, list(dt.children)
('/', None, [])
>>> ensure_dataset(dt).identical(ds)
True
>>> unwrap_data_source(dt).identical(da)
True

An existing tree node retains its location and parent:

>>> tree = xr.DataTree.from_dict({"measurement": ds})
>>> node = tree["measurement"]
>>> ensure_datatree(node) is node
True
>>> ensure_dataset(node).identical(ds)
True
>>> node.path
'/measurement'

Notes
-----
``unwrap_data_source`` recovers DataArrays from containers created by these
helpers. Other Datasets are returned unchanged, including single-variable
Datasets. For a DataTree, unwrapping reads the supplied node's Dataset.
"""

from __future__ import annotations

import xarray as xr

type XarraySourceT = xr.Dataset | xr.DataArray | xr.DataTree
"""Dataset, DataArray, or DataTree accepted by xarray adapters."""
type XarrayPayloadT = xr.Dataset | xr.DataArray
"""Dataset or DataArray exposed by an xarray accessor after unwrapping."""

_DATAARRAY_WRAPPER_ATTR = "_tollan_accessor_xarray_dataarray_name"
_MISSING = object()

__all__ = [
    "XarrayPayloadT",
    "XarraySourceT",
    "ensure_dataset",
    "ensure_datatree",
    "unwrap_data_source",
]


def unwrap_data_source(
    data_source: XarraySourceT,
) -> XarrayPayloadT:
    """Recover a wrapped DataArray or return the supplied Dataset.

    Parameters
    ----------
    data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
        Input object. For a tree, use the Dataset at the supplied node.

    Returns
    -------
    xarray.Dataset or xarray.DataArray
        A DataArray input is returned unchanged. A Dataset created from a
        DataArray by ``ensure_dataset`` yields that array with its name and
        attributes. Other Datasets are returned unchanged. For a DataTree,
        apply this selection to the supplied node's Dataset. Array storage
        is shared with the input.

    Raises
    ------
    ValueError
        The stored DataArray name is invalid or its variable is absent.
    """
    if isinstance(data_source, xr.DataTree):
        data_source = data_source.dataset

    if isinstance(data_source, xr.Dataset):
        dataarray_name = data_source.attrs.get(_DATAARRAY_WRAPPER_ATTR, _MISSING)
        if dataarray_name is not _MISSING:
            if (
                not isinstance(dataarray_name, str)
                or dataarray_name not in data_source.data_vars
            ):
                msg = f"Invalid {_DATAARRAY_WRAPPER_ATTR!r} marker: {dataarray_name!r}"
                raise ValueError(msg)
            return data_source[dataarray_name]
    return data_source


def ensure_datatree(data_source: XarraySourceT) -> xr.DataTree:
    """Return the input as a DataTree node.

    Parameters
    ----------
    data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
        Object to represent as a tree node.

    Returns
    -------
    xarray.DataTree
        A DataTree input is returned unchanged, including its parent relationship.
        A Dataset is placed at a new root with no children and ``name=None``.
        A DataArray occupies one variable named after the array, or ``data``
        when unnamed. The new tree shares the input arrays.

    Raises
    ------
    TypeError
        The input is not a Dataset, DataArray, or DataTree.
    """
    if isinstance(data_source, xr.DataTree):
        return data_source

    return xr.DataTree(dataset=ensure_dataset(data_source))


def ensure_dataset(data_source: XarraySourceT) -> xr.Dataset:
    """Return the input as a Dataset.

    Parameters
    ----------
    data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
        Object to represent as a Dataset.

    Returns
    -------
    xarray.Dataset
        A Dataset input is returned unchanged. A DataTree yields its
        ``dataset`` view at the supplied node, including inherited coordinates.
        A DataArray occupies one variable using its name or ``"data"``. Its
        attributes stay on that variable, and ``unwrap_data_source`` can recover
        it. All three cases share the input's array storage.

    Raises
    ------
    TypeError
        The input is not a Dataset, DataArray, or DataTree.
    """
    if isinstance(data_source, xr.Dataset):
        return data_source

    if isinstance(data_source, xr.DataTree):
        return data_source.dataset

    if isinstance(data_source, xr.DataArray):
        name = data_source.name or "data"
        result = xr.Dataset({name: data_source})
        result.attrs[_DATAARRAY_WRAPPER_ATTR] = name
        return result

    msg = f"Expected Dataset, DataArray, or DataTree, got {type(data_source)}"
    raise TypeError(msg)
