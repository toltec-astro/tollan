"""Tests for schema and mapping value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from tollan.accessor.schema import (
    MISSING,
    MappedField,
    MappedFieldSource,
    Mapping,
    MappingContext,
    NameMapping,
    Schema,
    SubpathMapping,
)


class TestNameMapping:
    """Test the concrete ordered-name mapping."""

    def test_frozen(self):
        """Mapping is immutable."""
        from pydantic_core import ValidationError

        fm = NameMapping("field")
        with pytest.raises(
            (AttributeError, ValidationError, TypeError),
        ):  # FrozenInstanceError
            fm.names = ("other",)  # ty: ignore[invalid-assignment]

    def test_invalid_names_elements(self):
        """Non-string elements in names raises error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):  # Validation error
            NameMapping([1, 2, 3])  # ty: ignore[invalid-argument-type]

    @pytest.mark.parametrize("mapping_cls", [NameMapping, SubpathMapping])
    def test_rejects_empty_names(self, mapping_cls):
        """At least one physical name is required."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            mapping_cls(candidates=())
        error = exc_info.value.errors()[0]
        assert error["loc"] == ("candidates",)
        assert error["type"] == "too_short"

    @pytest.mark.parametrize("mapping_cls", [NameMapping, SubpathMapping])
    def test_schema_requires_candidates(self, mapping_cls):
        """The schema exposes the nonempty candidates constraint."""
        from pydantic import TypeAdapter

        schema = TypeAdapter(mapping_cls).json_schema()
        if "$ref" in schema:
            schema = schema["$defs"][schema["$ref"].rsplit("/", 1)[1]]
        assert schema["properties"]["candidates"]["minItems"] == 1

    def test_rejects_duplicate_names(self):
        """Repeated candidates cannot affect resolution and are rejected."""
        with pytest.raises(ValueError, match="unique"):
            NameMapping(("field", "field"))


class TestMapping:
    """Test the public mapping strategy contract."""

    def test_unimplemented_resolve(self):
        """A strategy must implement resolve()."""

        class IncompleteMapping(Mapping):
            pass

        m = IncompleteMapping()
        with pytest.raises(NotImplementedError):
            m.resolve(MappingContext(None, Schema(), {}))


class TestMappingContext:
    """Test the short-lived mapping resolution context."""

    def test_frozen(self):
        """Resolution inputs cannot be rebound by a strategy."""
        schema = Schema()
        context = MappingContext({}, schema, {})
        with pytest.raises(FrozenInstanceError):
            context.data_source = {"other": 1}  # ty: ignore[invalid-assignment]


class TestMappedField:
    """Test MappedField result dataclass."""

    def test_basic_creation(self):
        """Basic MappedField creation."""
        fm = NameMapping("temp")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="temperature",
            value=25.0,
        )
        assert mf.mapping is fm
        assert mf.mapping_resolved is fm
        assert mf.name == "temperature"
        assert mf.value == 25.0
        assert mf.value_default is MISSING
        assert mf.source == MappedFieldSource.data_source

    def test_with_missing_value(self):
        """MappedField with MISSING value."""
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="",
            value=MISSING,
            source=MappedFieldSource.missing,
        )
        assert mf.value is MISSING
        assert mf.source == MappedFieldSource.missing

    def test_with_default_value(self):
        """MappedField with default value."""
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="",
            value_default=0.0,
            source=MappedFieldSource.default,
        )
        assert mf.value is MISSING
        assert mf.value_default == 0.0
        assert mf.source == MappedFieldSource.default

    def test_with_schema_path(self):
        """MappedField with schema path."""
        fm = NameMapping("field")
        mf = MappedField(
            mapping=fm,
            mapping_resolved=fm,
            name="physical_field",
            value=123,
            schema_path="MySchema.field",
        )
        assert mf.schema_path == "MySchema.field"


class TestSchema:
    """Test Schema base class."""

    def test_basic_schema(self):
        """Basic schema definition."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temperature")
            pressure: Mapping = NameMapping("pressure")

        schema = TestSchema()
        assert isinstance(schema.temp, NameMapping)
        assert isinstance(schema.pressure, NameMapping)
        assert isinstance(schema.temp, Mapping)
        assert isinstance(schema.pressure, Mapping)
        assert schema.temp.names == ("temperature",)

    def test_schema_with_alternatives(self):
        """Schema with alternative field names."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping(("temp_c", "temperature", "T"))

        schema = TestSchema()
        assert isinstance(schema.temp, NameMapping)
        assert schema.temp.names == ("temp_c", "temperature", "T")

    def test_get_schema_path(self):
        """get_schema_path() builds dotted path."""

        @dataclass
        class TestSchema(Schema):
            temp: Mapping = NameMapping("temperature")

        path = TestSchema.get_schema_path("temp")
        assert path == "TestSchema.temp"


class TestMappedFieldSource:
    """Test MappedFieldSource enum."""

    def test_enum_values(self):
        """Enum has correct values."""
        assert {
            name: member.value for name, member in MappedFieldSource.__members__.items()
        } == {
            "data_source": "data_source",
            "default": "default",
            "missing": "missing",
        }
        for member in MappedFieldSource:
            assert str(member) == member.value
            assert MappedFieldSource(member.value) is member


class TestMissingSentinel:
    """Test MISSING sentinel value."""

    def test_missing_repr(self):
        """MISSING has readable repr."""
        assert repr(MISSING) == "MISSING"


@pytest.mark.parametrize("path", ["", "/", ".", "..", "/absolute", "a/../b"])
def test_subpath_mapping_rejects_non_descendants(path):
    from pydantic import TypeAdapter

    from tollan.accessor import SubpathMapping
    from tollan.config.types import SubPath

    with pytest.raises(ValueError, match="relative descendant"):
        TypeAdapter(SubPath).validate_python(path)
    with pytest.raises(ValueError, match="relative descendant"):
        SubpathMapping.path(("valid", path))


@pytest.mark.parametrize("path", ["a/b", "a//b", "a/./b", "./a/b/"])
def test_subpath_mapping_and_field_share_normalization(path):
    from pydantic import TypeAdapter

    from tollan.accessor import SubpathMapping
    from tollan.config.types import SubPath

    subpath = TypeAdapter(SubPath).validate_python(path)
    mapping = SubpathMapping.path((path, "fallback"))
    assert mapping.names == (subpath.as_posix(), "fallback") == ("a/b", "fallback")


def test_subpath_mapping_rejects_duplicate_normalized_candidates():
    from tollan.accessor import SubpathMapping

    with pytest.raises(ValueError, match="candidates must be unique"):
        SubpathMapping.path(("a/b", "a/./b"))


def test_subpath_mapping_nested_validation_and_json_roundtrip():
    from pydantic import TypeAdapter, ValidationError

    from tollan.accessor import SubpathMapping

    adapter = TypeAdapter(SubpathMapping)
    mapping = adapter.validate_python({"candidates": [("./a//b/", "path")]})
    assert mapping.names == ("a/b",)
    assert adapter.validate_json(adapter.dump_json(mapping)) == mapping

    with pytest.raises(ValidationError) as exc_info:
        adapter.validate_python({"candidates": [("../a", "path")]})
    assert exc_info.value.errors()[0]["loc"] == ("candidates", 0, 0)


def test_subpath_mapping_retains_general_path_semantics_separately():
    from pydantic import ValidationError

    from tollan.accessor import SubpathMapping

    mapping = SubpathMapping.path(("sweep", "_input"))
    assert isinstance(mapping, NameMapping)
    assert mapping.names == ("sweep", "_input")
    assert NameMapping.path((".", "../sibling", "/root")).names == (
        ".",
        "../sibling",
        "/root",
    )
    with pytest.raises(ValidationError) as exc_info:
        SubpathMapping.var("data")
    assert exc_info.value.errors()[0]["type"] == "literal_error"
