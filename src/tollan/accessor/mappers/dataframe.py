"""pandas DataFrame-specific mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

from ..mapper import Mapper
from ..schema import Schema

__all__ = ["DataFrameMapper"]


class DataFrameMapper[SchemaT: Schema = Schema](Mapper[SchemaT]):
    """Mapper for pandas.DataFrame.

    Create via factory methods:
    - DataFrameMapper.from_data_source(dataframe)
    - DataFrameMapper.from_resolved(resolved_dict)

    Type Parameters
    ---------------
    SchemaT : Schema
        Schema type for this mapper (enables proper type hints)

    Parameters
    ----------
    resolved : dict[int, MappedField]
        Pre-resolved field mappings
    """

    data_source: pd.DataFrame

    def _has_field(self, name: str) -> bool:
        """Check if field exists as column or attribute."""
        return name in self.data_source.columns or name in self.data_source.attrs

    def _read_value(self, name: str) -> Any:
        """Read column value or attribute from dataframe.

        Returns the underlying numpy array for columns,
        or the raw attribute value for attrs.
        """
        if name in self.data_source.attrs:
            return self.data_source.attrs[name]
        return self.data_source[name].to_numpy()
