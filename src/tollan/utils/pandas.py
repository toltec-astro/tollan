"""Pandas row queries and collection-membership and bitmask predicates."""

from __future__ import annotations

from enum import Flag
from functools import partial
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    import collections.abc
    from typing import Any

__all__ = ["bits_all_set", "bits_any_set", "contains", "query"]

_COLLECTION_TYPES = (list, tuple, set, frozenset, np.ndarray)


def _contains(value: object, items: Any) -> bool:
    if isinstance(items, _COLLECTION_TYPES):
        return value in items
    if pd.api.types.is_scalar(items) and pd.isna(items):
        return False
    msg = "contains() requires list, tuple, set, frozenset or ndarray cells"
    raise TypeError(msg)


def contains(values: pd.Series, value: object) -> pd.Series:
    """Test exact element membership in each collection.

    Parameters
    ----------
    values : pandas.Series
        List, tuple, set, frozenset or NumPy array cells. Empty and missing cells
        do not match.
    value : object
        Element to find. Strings are compared exactly, not as substrings or regexes.

    Returns
    -------
    pandas.Series
        Boolean mask with the input index.

    Raises
    ------
    TypeError
        A non-null cell is not a supported collection, including string cells.

    Examples
    --------
    >>> import pandas as pd
    >>> tags = pd.Series([["science"], ["engineering"], [], None])
    >>> contains(tags, "science").tolist()
    [True, False, False, False]
    """
    return (
        values.map(partial(_contains, value), na_action="ignore")
        .fillna(value=False)
        .astype(bool)
    )


def bits_any_set(values: pd.Series, mask: int | Flag) -> pd.Series:
    """Test whether any bits in a mask are set in each value.

    Parameters
    ----------
    values : pandas.Series
        Integer bitmasks or an object column of enum flags. Nulls remain unknown.
    mask : int or enum.Flag
        Bits to test. Object columns require an enum flag; values belonging to
        other enum types do not match, even when their bit values are equal.

    Returns
    -------
    pandas.Series
        Boolean mask with the input index. A zero mask matches no non-null value.

    Raises
    ------
    TypeError
        An object column is supplied with a non-enum mask.

    Examples
    --------
    >>> import pandas as pd
    >>> bits_any_set(pd.Series([0, 1, 2, 3]), 3).tolist()
    [False, True, True, True]
    """
    if values.dtype == object:
        return _flag_bits(values, mask, all_bits=False)
    mask = mask.value if isinstance(mask, Flag) else mask
    return (values & mask) != 0


def bits_all_set(values: pd.Series, mask: int | Flag) -> pd.Series:
    """Test whether every bit in a mask is set in each value.

    Parameters
    ----------
    values : pandas.Series
        Integer bitmasks or an object column of enum flags. Nulls remain unknown.
    mask : int or enum.Flag
        Bits to test. Object columns require an enum flag; values belonging to
        other enum types do not match, even when their bit values are equal.

    Returns
    -------
    pandas.Series
        Boolean mask with the input index. A zero mask matches every non-null
        integer, or every non-null flag of the same enum type as the mask.

    Raises
    ------
    TypeError
        An object column is supplied with a non-enum mask.

    Examples
    --------
    >>> import pandas as pd
    >>> bits_all_set(pd.Series([0, 1, 2, 3]), 3).tolist()
    [False, False, False, True]
    """
    if values.dtype == object:
        return _flag_bits(values, mask, all_bits=True)
    mask = mask.value if isinstance(mask, Flag) else mask
    return (values & mask) == mask


def _flag_bits(values: pd.Series, mask: int | Flag, *, all_bits: bool) -> pd.Series:
    """Keep flag namespaces distinct in a mixed object column."""
    if not isinstance(mask, Flag):
        msg = "Enum-valued columns require an enum flag mask"
        raise TypeError(msg)
    comparable = values.where(values.map(type).isin([type(mask)]))
    matches = {
        value: ((value & mask) == mask if all_bits else bool(value & mask))
        for value in comparable.dropna().unique()
    }
    return (
        comparable.map(matches)
        .astype("boolean")
        .fillna(value=False)
        .mask(values.isna())
    )


_QUERY_NAMESPACE = {
    "contains": contains,
    "bits_any_set": bits_any_set,
    "bits_all_set": bits_all_set,
}


def query(
    table: pd.DataFrame,
    expression: str,
    *,
    namespace: collections.abc.Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Select rows using pandas expressions and shared query helpers.

    Parameters
    ----------
    table : pandas.DataFrame
        Table to query. The table is not modified.
    expression : str
        Pandas query expression evaluated with the Python engine. Only use
        trusted expressions; evaluation can execute arbitrary code.
    namespace : mapping of str to object, optional
        Additional constants and functions, referenced by name without ``@``.
        These override the built-in helpers; table columns take precedence over
        both. The mapping is not modified.

    Returns
    -------
    pandas.DataFrame
        Selected rows, preserving their index labels and order.

    Notes
    -----
    ``contains``, ``bits_any_set`` and ``bits_all_set`` are available by default.
    Comparisons, ``in`` and ``not in`` follow pandas query semantics.

    Examples
    --------
    >>> import pandas as pd
    >>> table = pd.DataFrame({"tags": [["science"], [], None], "exposure": [60, 30, 0]})
    >>> query(table, 'contains(tags, "science") and exposure > limit',
    ...       namespace={"limit": 30}).index.tolist()
    [0]
    """
    # Pandas mutates resolvers; protect the declarations and let columns win.
    namespace = {
        name: value
        for name, value in (_QUERY_NAMESPACE | dict(namespace or {})).items()
        if name not in table
    }
    return table.query(expression, engine="python", resolvers=[namespace])
