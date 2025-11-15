"""Tests for tollan.utils.py module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tollan.utils.py import (
    ObjectProxy,
    getname,
    getobj,
    module_from_path,
    rgetattr,
    rreload,
)


class TestObjectProxy:
    """Test ObjectProxy class."""

    def test_proxy_init_with_value(self):
        """Test initializing proxy with a direct value."""
        proxy = ObjectProxy()
        proxy.proxy_init(42)
        assert proxy.__wrapped__ == 42
        assert proxy.proxy_initialized()

    def test_proxy_init_with_factory(self):
        """Test initializing proxy with factory function."""

        def make_list(x, y):
            return [x, y]

        proxy = ObjectProxy(make_list)
        proxy.proxy_init(1, 2)
        assert proxy.__wrapped__ == [1, 2]
        assert proxy.proxy_initialized()

    def test_proxy_reset(self):
        """Test resetting proxy to uninitialized state."""
        proxy = ObjectProxy()
        proxy.proxy_init(42)
        assert proxy.proxy_initialized()
        proxy.proxy_reset()
        assert not proxy.proxy_initialized()
        assert proxy.__wrapped__ is None

    def test_proxy_initialized_false(self):
        """Test proxy_initialized returns False for uninitialized proxy."""
        proxy = ObjectProxy()
        assert not proxy.proxy_initialized()

    def test_proxy_init_no_args_raises(self):
        """Test that proxy_init with no factory and no args raises."""
        proxy = ObjectProxy()
        with pytest.raises(ValueError, match="too few arguments"):
            proxy.proxy_init()

    def test_proxy_init_too_many_args_raises(self):
        """Test that proxy_init with no factory and multiple args raises."""
        proxy = ObjectProxy()
        with pytest.raises(ValueError, match="too many arguments"):
            proxy.proxy_init(1, 2)

    def test_proxy_wraps_methods(self):
        """Test that proxy properly wraps object methods."""
        proxy: ObjectProxy[list[int]] = ObjectProxy()
        proxy.proxy_init([1, 2, 3])
        assert len(proxy) == 3  # type: ignore[arg-type]
        proxy.append(4)  # type: ignore[attr-defined]
        assert len(proxy) == 4  # type: ignore[arg-type]


class TestGetobj:
    """Test getobj function."""

    def test_getobj_import_module(self):
        """Test importing a module."""
        result = getobj("os")
        import os

        assert result is os

    def test_getobj_import_attribute(self):
        """Test importing a module attribute."""
        result = getobj("os.path:join")
        from os.path import join

        assert result is join

    def test_getobj_nested_attribute(self):
        """Test importing nested attributes."""
        result = getobj("os:path.join")
        from os.path import join

        assert result is join

    def test_getobj_with_default(self):
        """Test getobj returns default for non-existent module."""
        result = getobj("nonexistent_module_xyz", "default")
        assert result == "default"

    def test_getobj_raises_without_default(self):
        """Test getobj raises ImportError without default."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            getobj("nonexistent_module_xyz")

    def test_getobj_invalid_name_type(self):
        """Test getobj raises TypeError for non-string name."""
        with pytest.raises(TypeError, match="name must be a string"):
            getobj(123)  # type: ignore[arg-type]


class TestGetname:
    """Test getname function."""

    def test_getname_function(self):
        """Test getname on a function."""
        name = getname(TestGetname)
        assert "TestGetname" in name
        assert ":" in name

    def test_getname_builtin_function(self):
        """Test getname on builtin function."""
        name = getname(len)
        assert "len" in name

    def test_getname_class(self):
        """Test getname on a class."""
        name = getname(ObjectProxy)
        assert "ObjectProxy" in name
        assert ":" in name

    def test_getname_custom_separator(self):
        """Test getname with custom separator."""
        name = getname(ObjectProxy, sep=".")
        assert "." in name
        assert "ObjectProxy" in name

    def test_getname_invalid_object(self):
        """Test getname raises TypeError for object without __qualname__."""
        with pytest.raises(TypeError, match="invalid object type"):
            getname(42)


class TestModuleFromPath:
    """Test module_from_path function."""

    def test_module_from_path(self):
        """Test loading a module from file path."""
        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test_value = 123\n")
            temp_path = f.name

        try:
            module = module_from_path(temp_path)
            assert hasattr(module, "test_value")
            assert module.test_value == 123  # type: ignore[attr-defined]
        finally:
            Path(temp_path).unlink()

    def test_module_from_path_with_name(self):
        """Test loading a module with custom name."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 'hello'\n")
            temp_path = f.name

        try:
            module = module_from_path(temp_path, name="custom_module")
            assert module.__name__ == "custom_module"  # type: ignore[attr-defined]
            assert module.x == "hello"  # type: ignore[attr-defined]
        finally:
            Path(temp_path).unlink()

    def test_module_from_path_nonexistent_raises(self):
        """Test that nonexistent path raises ImportError."""
        with pytest.raises((ImportError, FileNotFoundError)):
            module_from_path("/nonexistent/path/file.py")


class TestRreload:
    """Test rreload function."""

    def test_rreload_single_module(self):
        """Test reloading a module."""
        # Import a module first
        import os

        # Reload it
        rreload(os)
        # Should still work
        assert hasattr(os, "path")

    def test_rreload_with_submodules(self):
        """Test reloading a package with submodules."""
        # This is hard to test comprehensively without creating temp packages
        # Just ensure it doesn't crash
        import json

        rreload(json)
        assert hasattr(json, "dumps")


class TestRgetattr:
    """Test rgetattr function."""

    def test_rgetattr_simple(self):
        """Test getting simple attribute."""

        class Obj:
            attr = 42

        assert rgetattr(Obj, "attr") == 42

    def test_rgetattr_nested(self):
        """Test getting nested attributes."""

        class Inner:
            value = 123

        class Outer:
            inner = Inner

        assert rgetattr(Outer, "inner.value") == 123

    def test_rgetattr_deeply_nested(self):
        """Test getting deeply nested attributes."""
        import os

        result = rgetattr(os, "path.join")
        from os.path import join

        assert result is join

    def test_rgetattr_with_default(self):
        """Test rgetattr with default value."""

        class Obj:
            pass

        assert rgetattr(Obj, "nonexistent", "default") == "default"

    def test_rgetattr_raises_without_default(self):
        """Test rgetattr raises AttributeError without default."""

        class Obj:
            pass

        with pytest.raises(AttributeError):
            rgetattr(Obj, "nonexistent")
