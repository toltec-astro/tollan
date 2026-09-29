"""Quantity-aware table projections of columnar xarray data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from astropy.table import QTable

from .units import UnitsAccessor
from .utils import ensure_dataset

if TYPE_CHECKING:
    from collections.abc import Mapping

    import xarray as xr

    from .utils import XarraySourceT

__all__ = ["dataset_to_qtable", "select_table_rows"]


def dataset_to_qtable(
    data_source: XarraySourceT,
    *,
    dim: str,
    columns: Mapping[str, str] | None = None,
    copy: bool = False,
) -> QTable:
    """Project one-dimensional columns into an in-memory quantity table.

    Parameters
    ----------
    data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
        Columnar data, or a tree node containing it. Dataset attributes become
        table metadata. Column ``units`` attributes are parsed by Astropy.
    dim : str
        Shared row dimension. Columns must have exactly this dimension.
    columns : mapping of str to str, optional
        Output column names mapped to source variable or coordinate names, in
        output order. By default, include all data variables in their order;
        coordinates must be requested explicitly.
    copy : bool, optional
        Copy column buffers when True. By default, share buffers where possible;
        edits to an in-memory table may affect the source and vice versa.

    Returns
    -------
    astropy.table.QTable
        Materialized columns, with units represented by Quantity columns.
        Unselected data variables are not loaded. No result is cached here.

    Raises
    ------
    KeyError
        The row dimension or a requested source column is absent.
    ValueError
        A column is not one-dimensional on ``dim``, or its unit is invalid.

    Notes
    -----
    This projection does not flatten, broadcast, or form a Cartesian product.
    Select rows before projecting to limit reads from lazy sources. Keep the
    source open until projection finishes. Table edits are not persisted to
    the source file.
    """
    dataset = ensure_dataset(data_source)
    if dim not in dataset.sizes:
        raise KeyError(dim)
    if columns is None:
        columns = {str(name): str(name) for name in dataset.data_vars}
    arrays = {}
    for name, source_name in columns.items():
        if source_name not in dataset.variables:
            raise KeyError(source_name)
        array = dataset[source_name]
        if array.dims != (dim,):
            msg = f"Table column {name!r} must have only dimension {dim!r}"
            raise ValueError(msg)
        arrays[name] = array
    return QTable(
        {
            name: UnitsAccessor(array.compute()).quantity
            for name, array in arrays.items()
        },
        copy=copy,
        meta=dict(dataset.attrs),
    )


def select_table_rows(
    data_source: XarraySourceT,
    mask: xr.DataArray,
    *,
    dim: str,
) -> xr.Dataset:
    """Select columnar rows by a positional boolean mask.

    Parameters
    ----------
    data_source : xarray.Dataset, xarray.DataArray, or xarray.DataTree
        Columnar data, or a tree node containing it.
    mask : xarray.DataArray
        Boolean mask with dimension ``dim`` and the source row count. Positions
        select rows; coordinate labels do not align or reorder the mask.
        Only the mask is materialized during selection.
    dim : str
        Row dimension to select.

    Returns
    -------
    xarray.Dataset
        Selected node's dataset with payload arrays remaining lazy. Contiguous
        selections use a slice and share in-memory column buffers. Scattered
        selections use integer indexing and may copy buffers.

    Raises
    ------
    KeyError
        The row dimension is absent.
    ValueError
        The mask has the wrong dimensions, length, or dtype.
    """
    dataset = ensure_dataset(data_source)
    n_rows = dataset.sizes[dim]
    if mask.dims != (dim,) or mask.size != n_rows or mask.dtype.kind != "b":
        msg = f"Expected a boolean mask with dimension {dim!r} and length {n_rows}"
        raise ValueError(msg)
    rows = np.flatnonzero(mask.to_numpy())
    if not rows.size:
        selector = slice(0, 0)
    elif np.all(np.diff(rows) == 1):
        selector = slice(int(rows[0]), int(rows[-1]) + 1)
    else:
        selector = rows
    return dataset.isel({dim: selector})
