"""Test astronomy types integration with config system."""

from __future__ import annotations

from typing import Any

import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from pydantic import TypeAdapter, ValidationError

from tollan.config import FrozenBaseModel, RuntimeConfig
from tollan.config.types import (
    AngleQuantityField,
    IsoTimeField,
    LengthQuantityField,
    QuantityField,
    SkyCoordField,
    TimeField,
    UnixTimeField,
    quantity_field,
    time_field,
)
from tollan.config.types.quantity import get_physical_type_from_quantity_type


class TestFrozenBaseModel:
    """Test FrozenBaseModel functionality."""

    def test_frozen_model(self):
        """Test that model is frozen after creation."""

        class TestModel(FrozenBaseModel):
            value: int

        model = TestModel(value=42)
        assert model.value == 42

        # Should raise validation error on frozen model
        with pytest.raises(ValidationError):
            model.value = 100  # ty: ignore[invalid-assignment]

    def test_yaml_roundtrip(self):
        """Test YAML serialization and deserialization."""

        class TestModel(FrozenBaseModel):
            name: str
            count: int

        model = TestModel(name="test", count=5)

        # Serialize to YAML
        yaml_str = model.model_dump_yaml()
        assert "name: test" in yaml_str
        assert "count: 5" in yaml_str

        # Deserialize from YAML
        loaded = TestModel.model_validate_yaml(yaml_str)
        assert loaded.name == "test"
        assert loaded.count == 5


class TestTimeFields:
    """Test Time field types."""

    def test_time_field_basic(self):
        """Test TimeField with ISO format."""

        class TestModel(FrozenBaseModel):
            obs_time: TimeField

        model = TestModel.model_validate({"obs_time": "2020-01-01T00:00:00"})
        assert isinstance(model.obs_time, Time)
        assert model.obs_time.isot == "2020-01-01T00:00:00.000"

    def test_iso_time_field(self):
        """Test IsoTimeField."""

        class TestModel(FrozenBaseModel):
            iso_time: IsoTimeField

        model = TestModel.model_validate({"iso_time": "2020-06-15T12:30:45"})
        assert isinstance(model.iso_time, Time)
        assert model.iso_time.format == "isot"

    def test_unix_time_field(self):
        """Test UnixTimeField."""

        class TestModel(FrozenBaseModel):
            unix_time: UnixTimeField

        # Unix timestamp for 2020-01-01 00:00:00 UTC
        model = TestModel.model_validate({"unix_time": 1577836800.0})
        assert isinstance(model.unix_time, Time)
        assert model.unix_time.format == "unix"

    def test_time_with_config_backend(self):
        """Test Time fields work with RuntimeConfig."""

        class ObsConfig(RuntimeConfig):
            start_time: IsoTimeField
            duration: float

        config = ObsConfig.model_validate(
            {"start_time": "2020-01-01T00:00:00", "duration": 3600.0},
        )
        assert isinstance(config.start_time, Time)
        assert config.duration == 3600.0

    @pytest.mark.parametrize(
        ("field_type", "raw", "serialized", "output_format"),
        [
            (TimeField, "2020-01-01T00:00:00", "2020-01-01T00:00:00.000", "isot"),
            (IsoTimeField, "2020-01-01 00:00:00", "2020-01-01T00:00:00.000", "isot"),
            (UnixTimeField, 1577836800.0, 1577836800.0, "unix"),
        ],
    )
    def test_time_json_roundtrip_and_schema(
        self,
        field_type,
        raw,
        serialized,
        output_format,
    ):
        """Each alias emits JSON it can validate back into the same instant."""
        adapter = TypeAdapter(field_type)
        value = adapter.validate_python(raw)
        dumped = adapter.dump_json(value)
        loaded = adapter.validate_json(dumped)

        assert adapter.dump_python(value) == serialized
        assert loaded.jd == pytest.approx(value.jd)
        assert adapter.json_schema(mode="serialization") == {
            "examples": [serialized],
            "format": "astropy-time",
            "type": "number" if isinstance(serialized, float) else "string",
            "x-tollan-output-format": output_format,
            "x-tollan-python-type": "astropy.time.Time",
            "x-tollan-scalar": True,
            **(
                {"x-tollan-time-formats": ["isot", "fits", "iso"]}
                if field_type is IsoTimeField
                else {
                    "x-tollan-time-formats": ["unix", "unix_tai"],
                }
                if field_type is UnixTimeField
                else {}
            ),
        }

    @pytest.mark.parametrize(
        ("value", "error_type"),
        [
            (object(), "time_type"),
            ("not-a-time", "time_parsing"),
            (Time(["2020-01-01", "2020-01-02"]), "time_scalar"),
        ],
    )
    def test_time_stable_validation_errors(self, value, error_type):
        """Bad user input always becomes a coded Pydantic ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TypeAdapter(TimeField).validate_python(value)
        assert exc_info.value.errors()[0]["type"] == error_type

    def test_time_factory_and_nested_container(self):
        """Dynamic annotations compose inside containers."""
        field_type = time_field(("unix",))
        container_type = list.__class_getitem__(field_type)
        adapter = TypeAdapter(container_type)
        values = adapter.validate_python([0.0])
        assert isinstance(values[0], Time)

    def test_string_time_roundtrip_normalizes_scale_to_utc(self):
        """String serialization preserves the instant for non-UTC inputs."""
        adapter = TypeAdapter(IsoTimeField)
        value = Time("2020-01-01T00:00:00", format="isot", scale="tai")
        loaded = adapter.validate_json(adapter.dump_json(value))
        assert loaded.utc.jd == pytest.approx(value.utc.jd)

    def test_time_parsing_returns_independent_values(self):
        """Neither string nor floating-point inputs are value-cached."""
        iso_adapter = TypeAdapter(IsoTimeField)
        first = iso_adapter.validate_python("2020-01-01T00:00:00")
        second = iso_adapter.validate_python("2020-01-01T00:00:00")

        assert first is not second
        first.precision = 1
        assert second.precision == 3

        unix_adapter = TypeAdapter(UnixTimeField)
        first_float = unix_adapter.validate_python(1577836800.25)
        second_float = unix_adapter.validate_python(1577836800.25)
        assert first_float is not second_float

    def test_time_factory_composes_in_union(self):
        """The public annotation factory composes in union fields."""
        field_type: Any = time_field(["isot"])

        value = TypeAdapter(field_type | None).validate_python("2020-01-01T00:00:00")
        assert isinstance(value, Time)


class TestQuantityFields:
    """Test Quantity field types."""

    def test_quantity_field_basic(self):
        """Test basic QuantityField."""

        class TestModel(FrozenBaseModel):
            distance: QuantityField

        model = TestModel.model_validate({"distance": "5.0 m"})
        assert isinstance(model.distance, u.Quantity)
        assert model.distance.value == 5.0
        assert model.distance.unit == u.m

    def test_length_quantity_field(self):
        """Test LengthQuantityField with physical type constraint."""

        class TestModel(FrozenBaseModel):
            width: LengthQuantityField

        model = TestModel.model_validate({"width": "10.0 cm"})
        assert isinstance(model.width, u.Quantity)
        assert model.width.value == 10.0
        assert model.width.unit == u.cm

        # This should fail because 'Hz' is not a length
        with pytest.raises(ValidationError):
            TestModel.model_validate({"width": "100 Hz"})

    def test_angle_quantity_field(self):
        """Test AngleQuantityField."""

        class TestModel(FrozenBaseModel):
            angle: AngleQuantityField

        model = TestModel.model_validate({"angle": "45.0 deg"})
        assert isinstance(model.angle, u.Quantity)
        assert model.angle.value == 45.0
        assert model.angle.unit == u.deg

    def test_quantity_with_config_backend(self):
        """Test Quantity fields work with RuntimeConfig."""

        class TelescopeConfig(RuntimeConfig):
            focal_length: LengthQuantityField
            field_of_view: AngleQuantityField

        config = TelescopeConfig.model_validate(
            {"focal_length": "10.0 m", "field_of_view": "1.0 arcmin"},
        )
        assert isinstance(config.focal_length, u.Quantity)
        assert config.focal_length.value == 10.0
        assert isinstance(config.field_of_view, u.Quantity)

    def test_quantity_json_roundtrip_and_schema(self):
        """Quantity metadata owns parsing, serialization, and both schemas."""
        adapter = TypeAdapter(LengthQuantityField)
        quantity = adapter.validate_json('"1.25 mm"')
        dumped = adapter.dump_json(quantity)
        loaded = adapter.validate_json(dumped)

        assert loaded == quantity
        assert adapter.dump_python(quantity) == "1.25 mm"
        assert adapter.json_schema(mode="validation") == {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
                {"type": "number"},
            ],
            "x-tollan-physical-types": ["length"],
            "x-tollan-python-type": "astropy.units.Quantity",
            "x-tollan-scalar": True,
        }
        assert adapter.json_schema(mode="serialization")["format"] == "quantity"

    @pytest.mark.parametrize(
        ("value", "error_type"),
        [
            (object(), "quantity_type"),
            ("not a quantity", "quantity_parsing"),
            (u.Quantity([1, 2], u.m), "quantity_scalar"),
            (1 * u.Hz, "quantity_physical_type"),
        ],
    )
    def test_quantity_stable_validation_errors(self, value, error_type):
        field_type = (
            LengthQuantityField
            if error_type == "quantity_physical_type"
            else QuantityField
        )
        with pytest.raises(ValidationError) as exc_info:
            TypeAdapter(field_type).validate_python(value)
        assert exc_info.value.errors()[0]["type"] == error_type

    def test_quantity_factory_composition_and_introspection(self):
        """Factories compose in containers and alias introspection is correct."""
        speed_field = quantity_field("speed")
        container_type = list.__class_getitem__(speed_field)
        values = TypeAdapter(container_type).validate_python(
            ["1 m / s", 2 * u.km / u.s]
        )
        assert all(
            value.unit.physical_type == u.get_physical_type("speed") for value in values
        )
        assert get_physical_type_from_quantity_type(
            LengthQuantityField
        ) == u.get_physical_type("length")
        assert get_physical_type_from_quantity_type(speed_field) == u.get_physical_type(
            "speed"
        )

    @pytest.mark.parametrize(
        ("physical_type", "raw", "expected"),
        [
            ("length", "10 m", 10 * u.m),
            ("time", "10 yr", 10 * u.year),
            ("mass", 10 * u.g, 10 * u.g),
            ("dimensionless", 1, 1 * u.dimensionless_unscaled),
        ],
    )
    def test_quantity_factory_historical_physical_types(
        self,
        physical_type,
        raw,
        expected,
    ):
        """Retain the physical-type cases covered by the pre-v3 test module."""
        value = TypeAdapter(quantity_field(physical_type)).validate_python(raw)
        assert value == expected

    def test_quantity_factory_composes_in_union(self):
        """The public annotation factory composes in union fields."""
        field_type: Any = quantity_field(["length"])

        value = TypeAdapter(field_type | None).validate_python("5 m")
        assert value == 5 * u.m


class TestSkyCoordField:
    """Test SkyCoord field type."""

    def test_skycoord_field_basic(self):
        """Test SkyCoordField with string coordinates."""

        class TestModel(FrozenBaseModel):
            target: SkyCoordField

        model = TestModel.model_validate({"target": "10:00:00 +20:00:00"})
        assert isinstance(model.target, SkyCoord)

    def test_skycoord_field_explicit_source_coordinates(self):
        """Test SkyCoordField with explicit M31 coordinates."""

        class TestModel(FrozenBaseModel):
            target: SkyCoordField

        model = TestModel.model_validate({"target": "10.6847083d 41.26875d"})
        assert isinstance(model.target, SkyCoord)
        assert model.target.ra.deg == pytest.approx(10.68, abs=1.0)  # pyright: ignore[reportOptionalMemberAccess]

    def test_skycoord_named_source_roundtrip(self, monkeypatch):
        """Source names resolve and remain names through JSON serialization."""

        class TestModel(FrozenBaseModel):
            target: SkyCoordField

        calls: list[str] = []

        def resolve(name: str) -> SkyCoord:
            calls.append(name)
            return SkyCoord("10.6847083d 41.26875d", frame="icrs")

        monkeypatch.setattr(SkyCoord, "from_name", staticmethod(resolve))
        model = TestModel.model_validate({"target": "M31"})
        loaded = TestModel.model_validate_json(model.model_dump_json())

        assert calls == ["M31", "M31"]
        assert isinstance(model.target, SkyCoord)
        assert model.target.ra.deg == pytest.approx(10.6847083)
        assert model.model_dump()["target"] == "M31"
        assert loaded.model_dump()["target"] == "M31"

    def test_skycoord_context_resolver_is_offline_safe(self):
        """Applications and tests can inject a deterministic name resolver."""
        adapter = TypeAdapter(SkyCoordField)

        def resolve(name: str) -> SkyCoord:
            assert name == "LMT"
            return SkyCoord("284.7625d -18.3147d")

        coord = adapter.validate_python(
            "LMT",
            context={"skycoord_name_resolver": resolve},
        )
        assert adapter.dump_python(coord) == "LMT"

    def test_skycoord_with_config_backend(self):
        """Test SkyCoord fields work with RuntimeConfig."""

        class ObservationConfig(RuntimeConfig):
            target: SkyCoordField
            duration: float

        config = ObservationConfig.model_validate(
            {"target": "12:00:00 +45:00:00", "duration": 1800.0},
        )
        assert isinstance(config.target, SkyCoord)
        assert config.duration == 1800.0

    def test_skycoord_json_roundtrip_and_schema(self):
        """Coordinates serialize canonically without mutating Astropy objects."""
        adapter = TypeAdapter(SkyCoordField)
        coord = SkyCoord("10.6847083d 41.26875d", frame="icrs")
        original_attrs = set(vars(coord))
        dumped = adapter.dump_json(adapter.validate_python(coord))
        loaded = adapter.validate_json(dumped)

        assert set(vars(coord)) == original_attrs
        assert coord.separation(loaded).to_value(u.arcsec) == pytest.approx(0, abs=1e-9)
        assert adapter.json_schema(mode="serialization")["format"] == "sky-coordinate"

    def test_skycoord_parsing_returns_independent_values(self):
        """Parsing never exposes shared mutable SkyCoord instances."""
        adapter = TypeAdapter(SkyCoordField)
        first = adapter.validate_python("10.6847083d 41.26875d")
        second = adapter.validate_python("10.6847083d 41.26875d")

        assert first is not second
        assert first.separation(second).to_value(u.arcsec) == pytest.approx(0)

    @pytest.mark.parametrize(
        ("ra", "dec"),
        [
            (72.34712708483526, 63.53595389117163),
            (12.123456789012345, -45.987654321098765),
            (359.99999999999994, 89.99999999999999),
            (1e-9, -1e-9),
        ],
    )
    def test_skycoord_retains_binary64_degrees(self, ra, dec):
        adapter = TypeAdapter(SkyCoordField)
        coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
        restored = adapter.validate_json(adapter.dump_json(coord))
        assert restored.ra.deg == coord.ra.deg
        assert restored.dec.deg == coord.dec.deg

    @pytest.mark.parametrize(
        ("value", "error_type"),
        [
            (object(), "skycoord_type"),
            (SkyCoord([1, 2] * u.deg, [3, 4] * u.deg), "skycoord_scalar"),
        ],
    )
    def test_skycoord_stable_validation_errors(self, value, error_type):
        with pytest.raises(ValidationError) as exc_info:
            TypeAdapter(SkyCoordField).validate_python(value)
        assert exc_info.value.errors()[0]["type"] == error_type

    def test_skycoord_name_resolution_error(self):
        def fail(_name: str) -> SkyCoord:
            raise ValueError

        with pytest.raises(ValidationError) as exc_info:
            TypeAdapter(SkyCoordField).validate_python(
                "not-a-source",
                context={"skycoord_name_resolver": fail},
            )
        assert exc_info.value.errors()[0]["type"] == "skycoord_name_resolution"


class TestComplexConfigWithTypes:
    """Test complex configuration using multiple astronomy types."""

    def test_full_observation_config(self):
        """Test a realistic observation configuration."""

        class InstrumentConfig(FrozenBaseModel):
            """Instrument configuration."""

            name: str
            wavelength: LengthQuantityField
            beam_size: AngleQuantityField

        class ObservationConfig(RuntimeConfig):
            """Full observation configuration."""

            target: SkyCoordField
            start_time: IsoTimeField
            exposure_time: float
            instrument: InstrumentConfig

        config_data = {
            "target": "M31",
            "start_time": "2020-01-01T00:00:00",
            "exposure_time": 3600.0,
            "instrument": {
                "name": "TolTEC",
                "wavelength": "1.1 mm",
                "beam_size": "5.0 arcsec",
            },
        }

        config = ObservationConfig.model_validate(
            config_data,
            context={
                "skycoord_name_resolver": lambda _name: SkyCoord(
                    "10.6847083d 41.26875d"
                )
            },
        )

        # Verify all fields
        assert isinstance(config.target, SkyCoord)
        assert isinstance(config.start_time, Time)
        assert config.exposure_time == 3600.0
        assert config.instrument.name == "TolTEC"
        assert isinstance(config.instrument.wavelength, u.Quantity)
        assert config.instrument.wavelength.unit == u.mm
        assert isinstance(config.instrument.beam_size, u.Quantity)
        assert config.instrument.beam_size.unit == u.arcsec

    def test_scientific_defaults_use_local_serializers(self):
        """Defaults serialize from field metadata without a global registry."""

        class Defaults(FrozenBaseModel):
            distance: LengthQuantityField = 1 * u.m
            timestamp: IsoTimeField = Time("2020-01-01T00:00:00")
            target: SkyCoordField = SkyCoord("1d 2d")

        model = Defaults()
        assert model.model_dump() == {
            "distance": "1.0 m",
            "timestamp": "2020-01-01T00:00:00.000",
            "target": "1d 2d",
        }
        schema = Defaults.model_json_schema(mode="serialization")
        assert schema["properties"]["distance"]["default"] == "1.0 m"
        assert schema["properties"]["timestamp"]["default"] == (
            "2020-01-01T00:00:00.000"
        )
        assert schema["properties"]["target"]["default"] == "1d 2d"

    def test_yaml_config_with_types(self):
        """Test loading config with astronomy types from YAML."""

        class TelescopeConfig(RuntimeConfig):
            """Telescope configuration."""

            name: str
            location: SkyCoordField
            altitude: LengthQuantityField
            commissioning_date: IsoTimeField

        yaml_config = """
        name: LMT
        location: "284.7625d -18.3147d"
        altitude: "4600 m"
        commissioning_date: "2011-11-16T00:00:00"
        """

        # Write to temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_config)
            yaml_file = f.name

        try:
            config = TelescopeConfig.model_validate_yaml(yaml_file)

            assert config.name == "LMT"
            assert isinstance(config.location, SkyCoord)
            assert isinstance(config.altitude, u.Quantity)
            assert config.altitude.value == 4600
            assert isinstance(config.commissioning_date, Time)
        finally:
            from pathlib import Path

            Path(yaml_file).unlink()
