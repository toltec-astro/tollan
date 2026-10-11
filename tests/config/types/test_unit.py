"""Astropy declaration fields validate and serialize inside ordinary models."""

import astropy.units as u
import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError

from tollan.config.types import AngleUnitField, PhysicalTypeField, UnitField, unit_field


class Representation(BaseModel):
    model_config = ConfigDict(strict=True, validate_default=True)

    unit: UnitField
    physical_type: PhysicalTypeField


@pytest.mark.parametrize(("unit", "name"), [("deg", "angle"), ("m / s", "speed")])
def test_astropy_declarations_work_without_arbitrary_types_config(unit, name):
    result = Representation.model_validate({"unit": unit, "physical_type": name})
    assert result.unit == u.Unit(unit)
    assert result.physical_type == u.get_physical_type(name)
    assert Representation.model_validate_json(result.model_dump_json()) == result
    assert result.model_dump()["unit"] is result.unit
    assert result.model_dump()["physical_type"] is result.physical_type
    assert TypeAdapter(UnitField).json_schema()["type"] == "string"


def test_existing_astropy_objects_are_preserved():
    unit = u.Hz
    physical_type = u.get_physical_type(unit)
    result = Representation(unit=unit, physical_type=physical_type)
    assert result.unit is unit
    assert result.physical_type is physical_type


def test_angle_constraint_applies_to_nested_fields_and_defaults():
    class Angles(BaseModel):
        model_config = ConfigDict(validate_default=True)
        units: list[AngleUnitField]

    result = Angles(units=["deg", u.rad])
    assert result.units == [u.deg, u.rad]
    assert Angles.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError) as exc:
        Angles(units=["deg", "s"])
    assert exc.value.errors()[0]["loc"] == ("units", 1)

    class InvalidDefault(BaseModel):
        model_config = ConfigDict(validate_default=True)
        unit: AngleUnitField = u.s

    with pytest.raises(ValidationError, match="physical type angle"):
        InvalidDefault()


def test_unit_annotation_factory():
    speed = TypeAdapter(unit_field("speed"))
    assert speed.validate_python("km/s") == u.km / u.s
    assert speed.validate_json(speed.dump_json(u.m / u.s)) == u.m / u.s
    with pytest.raises(ValidationError, match="physical type"):
        speed.validate_python(u.Hz)
    with pytest.raises(ValueError, match="not a known physical type"):
        unit_field("invalid physical type")
    assert TypeAdapter(unit_field()).validate_python("Hz") is u.Hz


@pytest.mark.parametrize("annotation", [UnitField, PhysicalTypeField])
@pytest.mark.parametrize("value", [object(), {}, "not an astropy value"])
def test_invalid_inputs_raise_validation_errors(annotation, value):
    with pytest.raises(ValidationError):
        TypeAdapter(annotation).validate_python(value)


def test_invalid_default_is_validated():
    class InvalidDefault(Representation):
        unit: UnitField = "invalid unit"  # ty: ignore[invalid-assignment] -- invalid default under test.

    with pytest.raises(ValidationError) as exc:
        InvalidDefault.model_validate({"physical_type": "angle"})
    assert exc.value.errors()[0]["loc"] == ("unit",)


def test_unnamed_physical_type_cannot_produce_unrestorable_json():
    physical_type = u.get_physical_type(u.m**37)
    adapter = TypeAdapter(PhysicalTypeField)
    assert adapter.validate_python(physical_type) is physical_type
    assert adapter.dump_python(physical_type) is physical_type
    with pytest.raises(PydanticSerializationError, match="registered name"):
        adapter.dump_json(physical_type)
