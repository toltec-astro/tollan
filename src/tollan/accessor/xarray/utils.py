"""Xarray utility functions for data source handling."""

from __future__ import annotations

import xarray as xr

type XarraySourceT = xr.Dataset | xr.DataArray | xr.DataTree

_DATAARRAY_WRAPPER_ATTR = "_tollan_accessor_xarray_dataarray_name"
_MISSING = object()

__all__ = [
    "XarraySourceT",
    "ensure_dataset",
    "ensure_datatree",
    "unwrap_data_source",
]


def unwrap_data_source(
    data_source: XarraySourceT,
) -> xr.Dataset | xr.DataArray:
    """Unwrap a DataTree node and any DataArray wrapper created here."""
    if isinstance(data_source, xr.DataTree):
        data_source = data_source.ds

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
    """Ensure data source is a DataTree.

    Wraps Dataset or DataArray in a DataTree, returns DataTree as-is.

    Parameters
    ----------
    data_source : Dataset, DataArray, or DataTree
        Data source to convert

    Returns
    -------
    xr.DataTree
        DataTree containing the data
    """
    if isinstance(data_source, xr.DataTree):
        return data_source

    if isinstance(data_source, xr.Dataset):
        return xr.DataTree(dataset=data_source, name="root")

    if isinstance(data_source, xr.DataArray):
        ds = ensure_dataset(data_source)
        return xr.DataTree(dataset=ds, name="root")

    msg = f"Expected Dataset, DataArray, or DataTree, got {type(data_source)}"
    raise TypeError(msg)


def ensure_dataset(data_source: XarraySourceT) -> xr.Dataset:
    """Ensure data source is a Dataset.

    Extracts Dataset from DataTree (root), wraps DataArray in Dataset,
    returns Dataset as-is.

    Parameters
    ----------
    data_source : Dataset, DataArray, or DataTree
        Data source to convert

    Returns
    -------
    xr.Dataset
        Dataset containing the data
    """
    if isinstance(data_source, xr.Dataset):
        return data_source

    if isinstance(data_source, xr.DataTree):
        # Return root dataset
        return data_source.ds

    if isinstance(data_source, xr.DataArray):
        name = data_source.name or "data"
        result = xr.Dataset({name: data_source})
        result.attrs[_DATAARRAY_WRAPPER_ATTR] = name
        return result

    msg = f"Expected Dataset, DataArray, or DataTree, got {type(data_source)}"
    raise TypeError(msg)
