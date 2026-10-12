"""Pydantic field types for configuration and scientific values.

These types validate configuration values and Astropy objects, including:

- Time fields with format constraints
- Quantity fields with physical type constraints
- SkyCoord fields for celestial coordinates
- Enhanced Path types with resolution and existence validation
- String selection by exact values or regular expressions
"""

from __future__ import annotations

from .fileloc import FileLocField
from .path import (
    AbsAnyPath,
    AbsDirectoryPath,
    AbsFilePath,
    AnyPath,
    SubPath,
    SubPathOrRoot,
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
from .selector import StringSelector
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
    "StringSelector",
    "SubPath",
    "SubPathOrRoot",
    "TimeField",
    "TimeQuantityField",
    "UnitField",
    "UnixTimeField",
    "path_field",
    "quantity_field",
    "time_field",
    "unit_field",
]
