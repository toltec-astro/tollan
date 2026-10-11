"""Custom pydantic types for astronomy data validation.

This module provides custom Pydantic types for validating astronomy-specific
data structures using astropy, including:

- Time fields with format constraints
- Quantity fields with physical type constraints
- SkyCoord fields for celestial coordinates
- Enhanced Path types with resolution and existence validation
"""

from __future__ import annotations

from .fileloc import FileLocField
from .path import (
    AbsAnyPath,
    AbsDirectoryPath,
    AbsFilePath,
    AnyPath,
    SubPath,
    path_field,
)
from .pydantic import FieldDefaults
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
from .unit import AngleUnitField, PhysicalTypeField, UnitField, unit_field

__all__ = [
    "AbsAnyPath",
    "AbsDirectoryPath",
    "AbsFilePath",
    "AngleQuantityField",
    "AngleUnitField",
    "AnyPath",
    "DimensionlessQuantityField",
    "FieldDefaults",
    "FileLocField",
    "FrequencyQuantityField",
    "IsoTimeField",
    "LengthQuantityField",
    "PhysicalTypeField",
    "QuantityField",
    "SkyCoordField",
    "SubPath",
    "TimeField",
    "TimeQuantityField",
    "UnitField",
    "UnixTimeField",
    "path_field",
    "quantity_field",
    "time_field",
    "unit_field",
]
