"""Xarray utility functions for data source handling."""

from __future__ import annotations

import xarray as xr

type DataSourceT = xr.Dataset | xr.DataArray | xr.DataTree

__all__ = [
    "DataSourceT",
    "ensure_dataset",
    "ensure_datatree",
]


def ensure_datatree(data_source: DataSourceT) -> xr.DataTree:
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
        # Wrap DataArray in Dataset
        name = data_source.name or "data"
        ds = xr.Dataset({name: data_source})
        return xr.DataTree(dataset=ds, name="root")

    msg = f"Expected Dataset, DataArray, or DataTree, got {type(data_source)}"
    raise TypeError(msg)


def ensure_dataset(data_source: DataSourceT) -> xr.Dataset:
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
        # Wrap DataArray in Dataset
        name = data_source.name or "data"
        return xr.Dataset({name: data_source})

    msg = f"Expected Dataset, DataArray, or DataTree, got {type(data_source)}"
    raise TypeError(msg)
