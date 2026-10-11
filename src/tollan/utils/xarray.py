"""Lazy median and scatter reductions for labeled xarray data.

``reduce_median_mad`` summarizes real-valued DataArrays or Dataset variables
along one dimension, retaining other dimensions, coordinates, and unit attributes.
Select or normalize values before reduction to control which samples contribute
and their relative scales.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from ..accessor.xarray import ensure_dataset

__all__ = ["reduce_median_mad"]


def reduce_median_mad(
    data: xr.DataArray | xr.Dataset, *, dim: str
) -> tuple[xr.Dataset, xr.Dataset]:
    """Reduce real-valued data to a median and scaled MAD along one dimension.

    Parameters
    ----------
    data : xarray.DataArray or xarray.Dataset
        Real-valued samples to summarize. Only variables carrying ``dim`` participate.
        Select or normalize the supplied values before calling to choose which
        samples and relative scales to combine.
    dim : str
        Dimension to reduce. Other dimensions of participating variables are retained.

    Returns
    -------
    median : xarray.Dataset
        Median of each participating variable along ``dim``. An unnamed DataArray
        uses the variable name ``data``.
    mad_std : xarray.Dataset
        Median absolute deviation from ``median``, multiplied by 1.4826.
        Describes scatter among samples, not uncertainty in the median.

        Both outputs are lazy, including for NumPy input. Names and dataset/variable
        attributes (including units) are retained. Coordinates of participating
        variables are retained unless they depend on ``dim``. NaNs propagate
        in each reduced slice. Each variable follows NumPy's median dtype rules:
        integer inputs yield float64; float32 and float64 retain their precision.

    Raises
    ------
    ValueError
        No variables carry the requested dimension, or that dimension is empty.

    Notes
    -----
    Variable selection and dimension checks occur immediately; numerical work
    runs on ``compute()`` or ``persist()``. Keep source files available until the
    results have been loaded; xarray can reopen path-based sources as needed.
    Each task needs the full reduction dimension in
    memory; select samples and chunk the other dimensions to limit memory use.
    Compute the two outputs together with :func:`dask.compute` to share work.

    Examples
    --------
    >>> import xarray as xr
    >>> from astropy import units as u
    >>> from tollan.utils.xarray import reduce_median_mad
    >>> values = xr.DataArray([1.0, 2.0, 8.0], dims="sample", name="signal").u.set(u.V)
    >>> median, mad_std = reduce_median_mad(values, dim="sample")
    >>> median.signal.compute().item()
    2.0
    >>> mad_std.signal.compute().item()
    1.4826
    >>> mad_std.signal.u.unit
    Unit("V")
    """
    data = ensure_dataset(data)
    names = [name for name, arr in data.data_vars.items() if dim in arr.dims]
    if not names:
        msg = f"No variables on dimension {dim!r}"
        raise ValueError(msg)
    if data.sizes[dim] == 0:
        msg = f"Cannot reduce empty dimension {dim!r}"
        raise ValueError(msg)
    data = data[names]

    def median(values: xr.Dataset) -> xr.Dataset:
        return xr.apply_ufunc(
            np.median,
            values.chunk({dim: -1}),
            input_core_dims=[[dim]],
            kwargs={"axis": -1},
            dask="parallelized",
            keep_attrs=True,
        )

    center = median(data)
    scatter = median(abs(data - center)) * 1.4826
    scatter.attrs = dict(data.attrs)
    for name in scatter.data_vars:
        scatter[name].attrs = dict(data[name].attrs)
    return center, scatter
