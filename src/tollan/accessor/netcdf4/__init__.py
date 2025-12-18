"""netCDF4-specific accessor components.

This module provides mapper implementation for netCDF4.Dataset objects.
"""

from __future__ import annotations

from .mapper import NetCDF4Mapper

__all__ = ["NetCDF4Mapper"]
