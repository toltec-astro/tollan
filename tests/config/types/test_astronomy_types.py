"""Test astronomy types integration with config system."""

from __future__ import annotations

import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from pydantic import ValidationError

from tollan.config import FrozenBaseModel, RuntimeConfig
from tollan.config.types import (
    AngleQuantityField,
    IsoTimeField,
    LengthQuantityField,
    QuantityField,
    SkyCoordField,
    TimeField,
    UnixTimeField,
)


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
            model.value = 100

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


class TestQuantityFields:
    """Test Quantity field types."""

    def test_quantity_field_basic(self):
        """Test basic QuantityField."""

        class TestModel(FrozenBaseModel):
            distance: QuantityField

        model = TestModel.model_validate({"distance": "5.0 m"})
        assert isinstance(model.distance, u.Quantity)
        assert model.distance.value == 5.0
        assert model.distance.unit == u.m  # type: ignore[attr-defined]

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
        assert model.angle.unit == u.deg  # type: ignore[attr-defined]

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


class TestSkyCoordField:
    """Test SkyCoord field type."""

    def test_skycoord_field_basic(self):
        """Test SkyCoordField with string coordinates."""

        class TestModel(FrozenBaseModel):
            target: SkyCoordField

        model = TestModel.model_validate({"target": "10:00:00 +20:00:00"})
        assert isinstance(model.target, SkyCoord)

    def test_skycoord_field_named_source(self):
        """Test SkyCoordField with named source."""

        class TestModel(FrozenBaseModel):
            target: SkyCoordField

        # Test with a well-known source name
        model = TestModel.model_validate({"target": "M31"})
        assert isinstance(model.target, SkyCoord)
        # M31 should be near RA=10.68deg, Dec=41.27deg
        assert model.target.ra.deg == pytest.approx(10.68, abs=1.0)  # type: ignore[attr-defined]

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

        config = ObservationConfig.model_validate(config_data)

        # Verify all fields
        assert isinstance(config.target, SkyCoord)
        assert isinstance(config.start_time, Time)
        assert config.exposure_time == 3600.0
        assert config.instrument.name == "TolTEC"
        assert isinstance(config.instrument.wavelength, u.Quantity)
        assert config.instrument.wavelength.unit == u.mm  # type: ignore[attr-defined]
        assert isinstance(config.instrument.beam_size, u.Quantity)
        assert config.instrument.beam_size.unit == u.arcsec  # type: ignore[attr-defined]

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
