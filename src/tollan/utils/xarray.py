"""Lazy median and scatter reductions for labeled xarray data.

``reduce_median_mad`` summarizes real-valued DataArrays or Dataset variables
along one dimension, retaining other dimensions, coordinates, and unit attributes.
Select or normalize values before reduction to control which samples contribute
and their relative scales.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from tollan.accessor.xarray import ensure_dataset

__all__ = ["reduce_median_mad"]


def reduce_median_mad(
    data: xr.DataArray | xr.Dataset, *, dim: str
) -> tuple[xr.Dataset, xr.Dataset]:
    """Reduce real-valued data to a median and scaled MAD along one dimension.

    Parameters
    ----------
    data : xarray.DataArray or xarray.Dataset
        Values to summarize. Only variables carrying ``dim`` participate.
        Select or normalize the supplied values before calling to choose which
        samples and relative scales to combine.
    dim : str
        Dimension to reduce. All other dimensions are retained.

    Returns
    -------
    median, mad_std : tuple of xarray.Dataset
        Lazy median and median absolute deviation multiplied by 1.4826.
        Variable names, units, and attributes are retained; an unnamed DataArray
        uses the variable name ``data``. NaNs propagate. The full reduction
        dimension is combined per task. The scaled MAD describes scatter among
        the supplied values, not uncertainty in the median.

    Raises
    ------
    ValueError
        No variables carry the requested dimension.

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
    data = data[names]

    def median(values: xr.Dataset) -> xr.Dataset:
        return xr.apply_ufunc(
            np.median,
            values.chunk({dim: -1}),
            input_core_dims=[[dim]],
            kwargs={"axis": -1},
            dask="parallelized",
            output_dtypes=[float],
            keep_attrs=True,
        )

    center = median(data)
    scatter = median(abs(data - center)) * 1.4826
    scatter.attrs = dict(data.attrs)
    for name in scatter.data_vars:
        scatter[name].attrs = dict(data[name].attrs)
    return center, scatter
