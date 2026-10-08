"""Tests for tollan.utils.py module."""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from weakref import ref

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
        proxy = cast("ObjectProxy[list[int]]", ObjectProxy())
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
            getobj(123)  # ty: ignore[invalid-argument-type]


class TestGetname:
    """Test getname function."""

    def test_getname_function(self):
        """Test getname on a function."""
        name = getname(rgetattr)
        assert name == "tollan.utils.py:rgetattr"
        assert getobj(name) is rgetattr

    def test_getname_builtin_function(self):
        """Test getname on builtin function."""
        name = getname(len)
        assert name == ":len"

    def test_getname_class(self):
        """Test getname on a class."""
        name = getname(ObjectProxy)
        assert name == "tollan.utils.py:ObjectProxy"
        assert getobj(name) is ObjectProxy

    def test_getname_custom_separator(self):
        """Test getname with custom separator."""
        name = getname(ObjectProxy, sep=".")
        assert name == "tollan.utils.py.ObjectProxy"

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
            assert module.test_value == 123  # pyright: ignore[reportAttributeAccessIssue]
        finally:
            Path(temp_path).unlink()

    def test_module_from_path_with_name(self):
        """Test loading a module with custom name."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 'hello'\n")
            temp_path = f.name

        try:
            module = module_from_path(temp_path, name="custom_module")
            assert module.__name__ == "custom_module"
            assert module.x == "hello"
        finally:
            Path(temp_path).unlink()

    def test_module_from_path_nonexistent_raises(self):
        """Test that nonexistent path raises ImportError."""
        with pytest.raises((ImportError, FileNotFoundError)):
            module_from_path("/nonexistent/path/file.py")


class TestRreload:
    """Test recursive reload using an isolated package."""

    def test_rreload_package_and_imported_child(self, tmp_path, monkeypatch):
        package = tmp_path / "audit_reload_package"
        package.mkdir()
        (package / "__init__.py").write_text(
            "from .child import value\npackage_value = 1\n"
        )
        (package / "child.py").write_text("value = 2\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        try:
            module = importlib.import_module("audit_reload_package")
            child = importlib.import_module("audit_reload_package.child")
            monkeypatch.setattr(module, "package_value", 99)
            monkeypatch.setattr(child, "value", 98)
            monkeypatch.setattr(module, "value", 97)
            rreload(module)
            assert child.value == 2
            assert module.value == 2
            assert module.package_value == 1
        finally:
            sys.modules.pop("audit_reload_package.child", None)
            sys.modules.pop("audit_reload_package", None)


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

    def test_rgetattr_preserves_present_none(self):
        obj = SimpleNamespace(inner=SimpleNamespace(value=None))
        assert rgetattr(obj, "inner.value", 42) is None
        assert rgetattr(SimpleNamespace(inner=None), "inner.value", 42) == 42

    def test_rgetattr_continues_through_intermediate_default(self):
        default = SimpleNamespace(value=42)
        assert rgetattr(SimpleNamespace(), "inner.value", default) == 42

    @pytest.mark.parametrize("error", [AttributeError, ValueError])
    def test_rgetattr_property_errors_follow_getattr(self, error):
        class Obj:
            @property
            def value(self):
                msg = "getter failed"
                raise error(msg)

        with pytest.raises(error, match="getter failed"):
            rgetattr(Obj(), "value")
        if error is AttributeError:
            assert rgetattr(Obj(), "value", 42) == 42
        else:
            with pytest.raises(error, match="getter failed"):
                rgetattr(Obj(), "value", 42)

    def test_rgetattr_reads_current_values_and_dynamic_attributes(self):
        calls = []

        class Obj:
            def __getattr__(self, name):
                calls.append(name)
                return len(calls)

        obj = Obj()
        assert rgetattr(obj, "value") == 1
        assert rgetattr(obj, "value") == 2
        assert rgetattr(Obj(), "value") == 3
        assert calls == ["value", "value", "value"]

    def test_rgetattr_accepts_unhashable_objects_and_defaults(self):
        class Obj:
            __hash__ = None

            def __init__(self):
                self.value = []

        obj = Obj()
        default = []
        assert rgetattr(obj, "value") is obj.value
        assert rgetattr(obj, "absent", default) is default
        default.append(1)
        assert rgetattr(obj, "absent", default) == [1]

    def test_rgetattr_does_not_retain_objects_or_defaults(self):
        class Obj:
            value = 1

        obj, default = Obj(), Obj()
        source_ref, default_ref = ref(obj), ref(default)
        assert rgetattr(obj, "value") == 1
        assert rgetattr(obj, "absent", default) is default
        del obj, default
        assert source_ref() is None
        assert default_ref() is None

    def test_rgetattr_extra_defaults_raise(self):
        with pytest.raises(TypeError):
            rgetattr(SimpleNamespace(), "value", 1, 2)
