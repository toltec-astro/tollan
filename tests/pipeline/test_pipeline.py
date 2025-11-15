"""Tests for pipeline context handlers."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from tollan.pipeline import (
    DictContextHandlerMixin,
    MetadataContextHandlerMixin,
)


# Test context classes
class SimpleContext(BaseModel):
    """Simple context for testing."""

    value: int
    name: str = "default"


class NestedContext(BaseModel):
    """Context with nested data."""

    count: int
    metadata: dict[str, str] = {}


# Test handlers
class SimpleDictHandler(DictContextHandlerMixin[str, SimpleContext]):
    """Handler for simple dict context."""

    _context_handler_context_cls = SimpleContext


class NestedDictHandler(DictContextHandlerMixin[str, NestedContext]):
    """Handler for nested context."""

    _context_handler_context_cls = NestedContext


class TestDictContextHandler:
    """Tests for DictContextHandlerMixin."""

    def test_create_context(self):
        """Test creating context in a dict."""
        data = {}
        ctx = SimpleDictHandler.create_context(data, {"value": 42, "name": "test"})

        assert ctx.value == 42
        assert ctx.name == "test"
        assert SimpleDictHandler.has_context(data)

    def test_get_context(self):
        """Test retrieving context from dict."""
        data = {}
        created = SimpleDictHandler.create_context(data, {"value": 100})
        retrieved = SimpleDictHandler.get_context(data)

        assert retrieved.value == 100
        assert retrieved.name == "default"
        assert created is retrieved  # Same object

    def test_has_context(self):
        """Test checking if context exists."""
        data = {}

        assert not SimpleDictHandler.has_context(data)

        SimpleDictHandler.create_context(data, {"value": 1})

        assert SimpleDictHandler.has_context(data)

    def test_get_or_create_existing(self):
        """Test get_or_create with existing context."""
        data = {}
        ctx1 = SimpleDictHandler.create_context(data, {"value": 1, "name": "first"})
        ctx2 = SimpleDictHandler.get_or_create_context(
            data,
            {"value": 999, "name": "second"},
        )

        # Should return existing context, not create new one
        assert ctx1 is ctx2
        assert ctx2.value == 1  # Original value
        assert ctx2.name == "first"  # Original name

    def test_get_or_create_new(self):
        """Test get_or_create when context doesn't exist."""
        data = {}
        ctx = SimpleDictHandler.get_or_create_context(data, {"value": 42})

        assert SimpleDictHandler.has_context(data)
        assert ctx.value == 42

    def test_nested_context(self):
        """Test context with nested data."""
        data = {}
        ctx = NestedDictHandler.create_context(
            data,
            {
                "count": 5,
                "metadata": {"source": "test", "version": "1.0"},
            },
        )

        assert ctx.count == 5
        assert ctx.metadata["source"] == "test"
        assert ctx.metadata["version"] == "1.0"

    def test_dict_data_conversion(self):
        """Test automatic conversion of dict data to context object."""
        data = {}
        key = SimpleDictHandler._context_handler_key()

        # Manually store dict data
        data[key] = {"value": 123, "name": "manual"}

        # get_context should convert it to context object
        ctx = SimpleDictHandler.get_context(data)

        assert isinstance(ctx, SimpleContext)
        assert ctx.value == 123
        assert ctx.name == "manual"

        # Should be cached as object now
        assert isinstance(data[key], SimpleContext)

    def test_multiple_handlers_same_dict(self):
        """Test multiple handlers using the same dict."""
        data = {}

        # Create contexts for both handlers
        SimpleDictHandler.create_context(data, {"value": 1})
        NestedDictHandler.create_context(data, {"count": 2})

        # Both should exist
        assert SimpleDictHandler.has_context(data)
        assert NestedDictHandler.has_context(data)

        # Retrieve both
        retrieved_simple = SimpleDictHandler.get_context(data)
        retrieved_nested = NestedDictHandler.get_context(data)

        assert retrieved_simple.value == 1
        assert retrieved_nested.count == 2


class MockMetadataObject:
    """Mock object with metadata attribute."""

    def __init__(self):
        self.meta = {}


class TableContext(BaseModel):
    """Context for table-like objects."""

    validated: bool = False
    source: str = "unknown"


class TableHandler(MetadataContextHandlerMixin[str, TableContext]):
    """Handler for table metadata context."""

    _context_handler_context_cls = TableContext


class TestMetadataContextHandler:
    """Tests for MetadataContextHandlerMixin."""

    def test_create_context_in_metadata(self):
        """Test creating context in object metadata."""
        obj = MockMetadataObject()
        ctx = TableHandler.create_context(obj, {"validated": True, "source": "test"})

        assert ctx.validated is True
        assert ctx.source == "test"
        assert TableHandler.has_context(obj)

    def test_get_context_from_metadata(self):
        """Test retrieving context from metadata."""
        obj = MockMetadataObject()
        created = TableHandler.create_context(obj, {"validated": True})
        retrieved = TableHandler.get_context(obj)

        assert retrieved.validated is True
        assert created is retrieved

    def test_no_metadata_attribute(self):
        """Test error when object has no .meta attribute."""
        obj = {}  # Dict has no .meta

        with pytest.raises(ValueError, match="has no .meta attribute"):
            TableHandler.create_context(obj, {"validated": True})

        with pytest.raises(ValueError, match="has no .meta attribute"):
            TableHandler.has_context(obj)

        with pytest.raises(ValueError, match="has no .meta attribute"):
            TableHandler.get_context(obj)

    def test_get_or_create_in_metadata(self):
        """Test get_or_create with metadata."""
        obj = MockMetadataObject()

        # First call creates
        ctx1 = TableHandler.get_or_create_context(obj, {"validated": False})
        assert ctx1.validated is False

        # Second call retrieves existing
        ctx2 = TableHandler.get_or_create_context(obj, {"validated": True})
        assert ctx2.validated is False  # Original value
        assert ctx1 is ctx2


class NonPydanticContext:
    """Non-Pydantic context class for testing."""

    def __init__(self, value: int, name: str = "default") -> None:
        self.value = value
        self.name = name


class NonPydanticHandler(DictContextHandlerMixin[str, NonPydanticContext]):
    """Handler for non-Pydantic context."""

    _context_handler_context_cls = NonPydanticContext


class TestNonPydanticContext:
    """Tests for non-Pydantic context classes."""

    def test_create_non_pydantic_context(self):
        """Test creating context with non-Pydantic class."""
        data = {}
        ctx = NonPydanticHandler.create_context(data, {"value": 42, "name": "test"})

        assert isinstance(ctx, NonPydanticContext)
        assert ctx.value == 42
        assert ctx.name == "test"

    def test_get_non_pydantic_context(self):
        """Test retrieving non-Pydantic context."""
        data = {}
        created = NonPydanticHandler.create_context(data, {"value": 100})
        retrieved = NonPydanticHandler.get_context(data)

        assert isinstance(retrieved, NonPydanticContext)
        assert retrieved.value == 100
        assert created is retrieved


class TestContextHandlerKey:
    """Tests for context handler key generation."""

    def test_unique_keys_for_different_handlers(self):
        """Test that different handlers get unique keys."""
        key1 = SimpleDictHandler._context_handler_key()
        key2 = NestedDictHandler._context_handler_key()
        key3 = TableHandler._context_handler_key()

        # All should be different
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3

        # Should be based on class names
        assert "SimpleDictHandler" in key1
        assert "NestedDictHandler" in key2
        assert "TableHandler" in key3
