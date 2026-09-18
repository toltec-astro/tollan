"""pandas DataFrame-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pandas as pd

from ..mapper import Mapper
from ..schema import FieldLocation, Schema

__all__ = ["DataFrameMapper"]


class DataFrameMapper[SchemaT: Schema = Schema](
    Mapper[SchemaT, "pd.DataFrame", "pd.Series"]
):
    """Mapper for pandas.DataFrame.

    Use get_col() and has_col() as aliases for get_var() and
    has_var(). Column reads return native Series with their index and dtype.

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)
    """

    _supported_locations: ClassVar = (FieldLocation.attr, FieldLocation.var)

    get_col = Mapper[SchemaT, "pd.DataFrame", "pd.Series"].get_var
    has_col = Mapper[SchemaT, "pd.DataFrame", "pd.Series"].has_var

    def _has_attr(self, data_source: pd.DataFrame, name: str) -> bool:
        """Check frame attributes without reading values."""
        return name in data_source.attrs

    def _has_var(self, data_source: pd.DataFrame, name: str) -> bool:
        """Check column names without reading values."""
        return name in data_source.columns

    def _get_attr(self, data_source: pd.DataFrame, name: str) -> Any:
        """Return a frame attribute unchanged."""
        return data_source.attrs[name]

    def _get_var(self, data_source: pd.DataFrame, name: str) -> pd.Series:
        """Return a native column with its index and dtype."""
        return data_source[name]

    def _read_var_values(self, var: pd.Series) -> Any:
        """Read column values as a NumPy array without its index."""
        return var.to_numpy()
