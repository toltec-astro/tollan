"""
Table validation utilities for astropy and pandas tables.

Provides unified helpers for working with both astropy Table/QTable
and pandas DataFrame objects.

Examples
--------
>>> from astropy.table import Table
>>> from tollan.utils.table import TableValidator
>>> tbl = Table([[1, 2, 3], [4, 5, 6]], names=['a', 'b'])
>>> TableValidator().has_all_cols(tbl, ['a', 'b'])
True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, assert_never, overload

import pandas as pd
from astropy.table import QTable, Table

__all__ = ["TableT", "TableValidator"]


TableT = Table | QTable | pd.DataFrame


@dataclass
class TableValidator:
    """
    Validator for astropy and pandas tables.

    Provides a unified interface for column and metadata validation across
    astropy Table/QTable and pandas DataFrame objects.
    """

    def _get_colnames(self, tbl: TableT) -> list[str]:
        if isinstance(tbl, Table):
            return tbl.colnames
        if isinstance(tbl, pd.DataFrame):
            return list(tbl.columns)
        assert_never(tbl)

    def validate_cols(self, tbl: TableT, cols: list[str]) -> list[str]:
        """
        Return the subset of columns in `cols` that exist in the table.

        Parameters
        ----------
        tbl : TableT
            Table to validate.
        cols : list[str]
            Column names to check.

        Returns
        -------
        list[str]
            Subset of `cols` that exist in `tbl`.
        """
        colnames = self._get_colnames(tbl)
        return [c for c in cols if c in colnames]

    def has_any_col(self, tbl: TableT, cols: list[str]) -> bool:
        """Return True if any of the specified columns exist in the table.

        Parameters
        ----------
        tbl : TableT
            Table to check
        cols : list[str]
            Column names to search for

        Returns
        -------
        bool
            True if any column in cols exists in table
        """
        return len(self.validate_cols(tbl, cols)) > 0

    def has_all_cols(self, tbl: TableT, cols: list[str]) -> bool:
        """Return True if all specified columns exist in the table.

        Parameters
        ----------
        tbl : TableT
            Table to check
        cols : list[str]
            Column names to search for

        Returns
        -------
        bool
            True if all columns in cols exist in table
        """
        return len(self.validate_cols(tbl, cols)) == len(cols)

    def get_first_col(self, tbl: TableT, cols: list[str]) -> str | None:
        """Return the first column in `cols` that exists in the table, or None.

        Parameters
        ----------
        tbl : TableT
            Table to search
        cols : list[str]
            Column names to search for

        Returns
        -------
        str | None
            First matching column name, or None if no match
        """
        cols_exist = self.validate_cols(tbl, cols)
        if not cols_exist:
            return None
        return cols_exist[0]

    def get_first_col_data(
        self,
        tbl: TableT,
        cols: list[str],
    ) -> Any | None:
        """Return data from the first column in `cols`.

        Parameters
        ----------
        tbl : TableT
            Table to retrieve data from
        cols : list[str]
            Column names to search for

        Returns
        -------
        Any | None
            Column data from first match, or None if no match
        """
        col = self.get_first_col(tbl, cols)
        return tbl[col] if col is not None else None

    def get_col_data(self, tbl: TableT, cols: list[str]) -> list[Any | None]:
        """Return a list of data for each column in `cols` (None if missing).

        Parameters
        ----------
        tbl : TableT
            Table to retrieve data from
        cols : list[str]
            Column names to retrieve

        Returns
        -------
        list[Any | None]
            List of column data (None for missing columns)
        """
        colnames = self._get_colnames(tbl)
        return [tbl[c] if c in colnames else None for c in cols]

    def validate_meta(self, meta: dict, keys: list[str]) -> list[str]:
        """Return the subset of keys in `keys` that exist in the metadata dict.

        Parameters
        ----------
        meta : dict
            Metadata dictionary to check
        keys : list[str]
            Keys to search for

        Returns
        -------
        list[str]
            Subset of keys that exist in meta
        """
        return [k for k in keys if k in meta]

    def has_any_meta(self, meta: dict, keys: list[str]) -> bool:
        """Return True if any of the specified keys exist in the metadata dict.

        Parameters
        ----------
        meta : dict
            Metadata dictionary to check
        keys : list[str]
            Keys to search for

        Returns
        -------
        bool
            True if any key exists in meta
        """
        return len(self.validate_meta(meta, keys)) > 0

    def has_all_meta(self, meta: dict, keys: list[str]) -> bool:
        """Return True if all specified keys exist in the metadata dict.

        Parameters
        ----------
        meta : dict
            Metadata dictionary to check
        keys : list[str]
            Keys to search for

        Returns
        -------
        bool
            True if all keys exist in meta
        """
        return len(self.validate_meta(meta, keys)) == len(keys)

    def get_first_meta(self, meta: dict, keys: list[str]) -> str | None:
        """Return the first key in `keys` that exists in the metadata dict, or None.

        Parameters
        ----------
        meta : dict
            Metadata dictionary to search
        keys : list[str]
            Keys to search for

        Returns
        -------
        str | None
            First matching key, or None if no match
        """
        keys_exist = self.validate_meta(meta, keys)
        if not keys_exist:
            return None
        return keys_exist[0]

    def get_first_meta_value(self, meta: dict, keys: list[str]) -> Any | None:
        """Return the value for the first key in `keys`.

        Parameters
        ----------
        meta : dict
            Metadata dictionary to retrieve from
        keys : list[str]
            Keys to search for

        Returns
        -------
        Any | None
            Value for first matching key, or None if no match
        """
        key = self.get_first_meta(meta, keys)
        return meta[key] if key is not None else None

    def get_meta_values(self, meta: dict, keys: list[str]) -> list[Any | None]:
        """Return a list of values for each key in `keys` (None if missing).

        Parameters
        ----------
        meta : dict
            Metadata dictionary to retrieve from
        keys : list[str]
            Keys to retrieve values for

        Returns
        -------
        list[Any | None]
            List of values (None for missing keys)
        """
        return [meta.get(k) for k in keys]

    def eval(self, tbl: TableT, expr: str, **kwargs: Any) -> Any:
        """Evaluate an expression on table columns.

        Parameters
        ----------
        tbl : TableT
            Table to evaluate expression on
        expr : str
            Expression to evaluate (column names available as variables)
        **kwargs
            Additional arguments passed to pd.eval or DataFrame.eval

        Returns
        -------
        Any
            Result of expression evaluation
        """
        if isinstance(tbl, Table):
            local_dict = kwargs.pop("local_dict", {}) | dict(tbl.columns)
            return pd.eval(expr, local_dict=local_dict, **kwargs)
        if isinstance(tbl, pd.DataFrame):
            return tbl.eval(expr, **kwargs)
        assert_never(tbl)

    @overload
    def query(self, tbl: pd.DataFrame, expr: str, **kwargs: Any) -> pd.DataFrame: ...

    @overload
    def query(
        self,
        tbl: Table | QTable,
        expr: str,
        **kwargs: Any,
    ) -> Table | QTable: ...

    def query(self, tbl: TableT, expr: str, **kwargs: Any) -> TableT:
        """Return a filtered table using a query expression.

        Parameters
        ----------
        tbl : TableT
            Table to filter
        expr : str
            Boolean expression for filtering rows
        **kwargs
            Additional arguments passed to query evaluation

        Returns
        -------
        TableT
            Filtered table with rows matching expression
        """
        if isinstance(tbl, Table):
            return tbl[self.eval(tbl, expr, **kwargs)]  # type: ignore[return-value]
        if isinstance(tbl, pd.DataFrame):
            return tbl.query(expr, **kwargs)
        assert_never(tbl)
