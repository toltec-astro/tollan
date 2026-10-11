"""Schema-based access and model-table projection for pandas DataFrames."""

from __future__ import annotations

from .mapper import DataFrameMapper
from .model_table import ModelTableAccessor

__all__ = ["DataFrameMapper", "ModelTableAccessor"]
