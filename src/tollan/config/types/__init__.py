"""Custom pydantic types for astronomy data validation.

This module provides custom Pydantic types for validating astronomy-specific
data structures using astropy, including:

- Time fields with format constraints
- Quantity fields with physical type constraints
- SkyCoord fields for celestial coordinates
- Enhanced Path types with resolution and existence validation
"""

from __future__ import annotations

from .path import AbsAnyPath, AbsDirectoryPath, AbsFilePath, AnyPath, PathValidator
from .pydantic import FieldDefaults, GenerateJsonSchema
from .quantity import (
    AngleQuantityField,
    DimensionlessQuantityField,
    FrequencyQuantityField,
    LengthQuantityField,
    QuantityField,
    TimeQuantityField,
    quantity_field,
)
from .skycoord import SkyCoordField
from .time import IsoTimeField, TimeField, UnixTimeField, time_field

__all__ = [
    # Path types
    "AbsAnyPath",
    "AbsDirectoryPath",
    "AbsFilePath",
    "AngleQuantityField",
    "AnyPath",
    "DimensionlessQuantityField",
    # Pydantic utilities
    "FieldDefaults",
    "FrequencyQuantityField",
    "GenerateJsonSchema",
    "IsoTimeField",
    "LengthQuantityField",
    "PathValidator",
    # Quantity types
    "QuantityField",
    # SkyCoord types
    "SkyCoordField",
    # Time types
    "TimeField",
    "TimeQuantityField",
    "UnixTimeField",
    "quantity_field",
    "time_field",
]
