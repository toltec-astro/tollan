"""Tests for tollan.utils.fileloc module."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from tollan.utils.fileloc import FileLoc, FileLocData, fileloc


class TestFileLocData:
    """Test FileLocData dataclass."""

    def test_from_file_url(self):
        """Test creating FileLocData from file:// URL."""
        fld = FileLocData("file:///a.b")
        assert fld.url_resolved.unicode_string() == "file:///a.b"
        assert not fld.netloc_resolved
        assert fld.path_resolved.name == "a.b"

    def test_from_fileloc_data(self):
        """Test creating FileLocData from another FileLocData."""
        fld = FileLocData("file:///a.b")
        fld2 = FileLocData(fld)
        assert fld2.url_resolved.unicode_string() == "file:///a.b"
        assert not fld2.netloc_resolved
        assert fld2.path_resolved.name == "a.b"

    def test_from_tuple_with_remote_parent(self):
        """Test creating FileLocData from tuple with remote parent path."""
        fld = FileLocData(("a", "b.c"), remote_parent_path="/remote")
        assert fld.url_resolved.unicode_string() == "file://a/remote/b.c"
        assert fld.netloc_resolved == fld.netloc == "a"
        assert fld.path_resolved.name == "b.c"

    def test_from_fileloc_data_preserves_context(self):
        """Test that context is preserved when creating from FileLocData."""
        fld = FileLocData(("a", "b.c"), remote_parent_path="/remote")
        fld2 = FileLocData(fld)
        assert fld2.url_resolved.unicode_string() == "file://a/remote/b.c"

    def test_conflict_on_revalidation(self):
        """Test that conflicting context raises error."""
        fld = FileLocData(("a", "b.c"), remote_parent_path="/remote")
        with pytest.raises(ValueError, match="remote_parent_path not allowed"):
            FileLocData(fld, remote_parent_path="/remote2")

    def test_from_path_object(self):
        """Test creating FileLocData from Path object."""
        p = Path("/data/test.txt")
        fld = FileLocData(p)
        assert fld.path == p
        assert fld.netloc == ""
        assert fld.path_resolved.name == "test.txt"

    def test_from_dict(self):
        """Test creating FileLocData from dict."""
        fld = FileLocData({"path": "/data/test.txt", "netloc": ""})
        assert fld.path == Path("/data/test.txt")
        assert fld.netloc == ""

    def test_localhost_treated_as_local(self):
        """Test that localhost netloc is treated as empty."""
        fld = FileLocData("localhost:/data/test.txt")
        assert fld.netloc == ""
        assert fld.netloc_resolved == ""

    def test_none_netloc_becomes_empty_string(self):
        """Test that None netloc becomes empty string."""
        fld = FileLocData({"path": "/data/test.txt", "netloc": None})
        assert fld.netloc == ""

    def test_windows_path_detection(self):
        """Test detection of Windows paths."""
        fld = FileLocData(r"C:\Users\test\file.txt")
        assert fld.path is not None
        assert fld.netloc == ""

    def test_remote_colon_syntax(self):
        """Test remote path with colon syntax."""
        fld = FileLocData("host:/path/to/file")
        assert fld.netloc == "host"
        assert str(fld.path) == "/path/to/file"

    def test_missing_url_and_path(self):
        """Test that missing both url and path raises error."""
        with pytest.raises(ValueError, match="url or path required"):
            FileLocData({})

    def test_local_parent_path_resolution(self):
        """Test local relative path resolution with parent."""
        fld = FileLocData("relative.txt", local_parent_path="/base/path")
        assert "/base/path" in str(fld.path_resolved)

    def test_remote_parent_path_resolution(self):
        """Test remote relative path resolution with parent."""
        fld = FileLocData(("host", "relative.txt"), remote_parent_path="/remote/base")
        assert "/remote/base" in str(fld.path_resolved)


class TestFileLoc:
    """Test FileLoc RootModel wrapper."""

    def test_from_file_url(self):
        """Test creating FileLoc from file:// URL."""
        fl = FileLoc.model_validate("file:///a.b")
        assert fl.url == "file:///a.b"
        assert not fl.netloc
        assert fl.path.name == "a.b"
        assert fl.is_local()

    def test_from_remote_file_url(self):
        """Test creating FileLoc from remote file:// URL."""
        fl = FileLoc.model_validate("file://a/b.c")
        assert fl.url == "file://a/b.c"
        assert fl.netloc == "a"
        assert fl.path.name == "b.c"
        assert fl.is_remote()

    def test_from_local_path_string(self):
        """Test creating FileLoc from local path string."""
        fl = FileLoc.model_validate("a.b")
        assert fl.url.endswith("a.b")
        assert not fl.netloc
        assert fl.path.name == "a.b"
        assert fl.is_local()

    def test_from_remote_colon_syntax(self):
        """Test creating FileLoc from remote colon syntax."""
        fl = FileLoc.model_validate("a:/b.c")
        assert fl.url == "file://a/b.c"
        assert fl.netloc == "a"
        assert fl.path.name == "b.c"
        assert fl.is_remote()

    def test_from_fileloc(self):
        """Test creating FileLoc from another FileLoc."""
        fl = FileLoc.model_validate("a:/b.c")
        fl2 = FileLoc.model_validate(fl)
        assert fl2.url == "file://a/b.c"
        assert fl2.netloc == "a"
        assert fl2.path.name == "b.c"
        assert fl2.is_remote()

    def test_scheme_property(self):
        """Test scheme property."""
        fl = FileLoc.model_validate("file:///data/test.txt")
        assert fl.scheme == "file"

    def test_host_property(self):
        """Test host property."""
        fl = FileLoc.model_validate("file://myhost/data/test.txt")
        assert fl.host == "myhost"

    def test_host_property_empty_for_local(self):
        """Test host property is empty for local files."""
        fl = FileLoc.model_validate("/data/test.txt")
        assert fl.host == ""

    def test_path_orig_property(self):
        """Test path_orig property returns unresolved path."""
        fl = FileLoc.model_validate("relative.txt")
        assert fl.path_orig == Path("relative.txt")

    def test_exists_for_local(self, tmp_path):
        """Test exists() for local files."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        fl = FileLoc.model_validate(str(test_file))
        assert fl.exists()

    def test_exists_false_for_nonexistent(self, tmp_path):
        """Test exists() returns False for nonexistent files."""
        test_file = tmp_path / "nonexistent.txt"
        fl = FileLoc.model_validate(str(test_file))
        assert not fl.exists()

    def test_exists_false_for_remote(self):
        """Test exists() returns False for remote files."""
        fl = FileLoc.model_validate("host:/data/test.txt")
        assert not fl.exists()

    def test_as_rsync_arg_local(self):
        """Test as_rsync_arg() for local files."""
        fl = FileLoc.model_validate("/data/test.txt")
        assert fl.as_rsync_arg() == "/data/test.txt"

    def test_as_rsync_arg_remote(self):
        """Test as_rsync_arg() for remote files."""
        fl = FileLoc.model_validate("host:/data/test.txt")
        assert fl.as_rsync_arg() == "host:/data/test.txt"

    def test_repr(self):
        """Test __repr__ method."""
        fl = FileLoc.model_validate("host:/data/test.txt")
        assert "FileLoc" in repr(fl)
        assert "host:/data/test.txt" in repr(fl)

    def test_from_http_url(self):
        """Test creating FileLoc from HTTP URL."""
        fl = FileLoc.model_validate("http://example.com/file.txt")
        assert fl.scheme == "http"
        assert fl.host == "example.com"
        assert fl.is_remote()

    def test_from_https_url(self):
        """Test creating FileLoc from HTTPS URL."""
        fl = FileLoc.model_validate("https://example.com/file.txt")
        assert fl.scheme == "https"
        assert fl.host == "example.com"
        assert fl.is_remote()


class TestFilelocFunction:
    """Test fileloc() convenience function."""

    def test_basic_usage(self):
        """Test basic fileloc() usage."""
        fl = fileloc("file:///a.b")
        assert fl.url == "file:///a.b"
        assert not fl.netloc
        assert fl.path.name == "a.b"

    def test_with_remote_parent(self):
        """Test fileloc() with remote parent path."""
        fl = fileloc(("a", "b.c"), remote_parent_path="/")
        assert fl.url == "file://a/b.c"
        assert fl.netloc == "a"
        assert fl.path.name == "b.c"
        assert fl.is_remote()

    def test_with_empty_netloc(self):
        """Test fileloc() with empty netloc."""
        fl = fileloc(("", "b.c"), remote_parent_path="/")
        assert re.match(r"file:///.+b\.c", fl.url)
        assert fl.netloc == ""
        assert fl.path.name == "b.c"
        assert fl.is_local()

    def test_localhost_with_local_parent(self):
        """Test fileloc() with localhost netloc and local parent."""
        fl = fileloc(
            ("localhost", "b.c"),
            remote_parent_path="/",
            local_parent_path="/local",
        )
        assert fl.url == "file:///local/b.c"
        assert fl.netloc == ""
        assert fl.path.name == "b.c"
        assert fl.is_local()

    def test_no_revalidate_by_default(self):
        """Test that revalidate defaults to False."""
        fl = fileloc("file:///a.b")
        fl2 = fileloc(fl, local_parent_path="/parent")
        assert fl2.url == fl.url

    def test_revalidate_true(self):
        """Test revalidate=True changes context."""
        fl = fileloc(("localhost", "b.c"), local_parent_path="/local")
        fl2 = fileloc(fl, local_parent_path="/parent", revalidate=True)
        assert fl2.url == "file:///parent/b.c"

    def test_with_local_parent_path(self):
        """Test fileloc() with local parent path."""
        fl = fileloc("relative.txt", local_parent_path="/base")
        assert "/base" in fl.url

    def test_from_path_object(self):
        """Test fileloc() from Path object."""
        p = Path("/data/test.txt")
        fl = fileloc(p)
        assert fl.path.name == "test.txt"


class TestFileLocRelativeRemote:
    """Test remote relative path validation."""

    def test_relative_remote_tuple_raises(self):
        """Test that relative remote path in tuple raises error."""
        with pytest.raises(ValueError, match="remote path shall be absolute"):
            fileloc(("a", "b.c"))

    def test_relative_remote_colon_raises(self):
        """Test that relative remote path with colon raises error."""
        with pytest.raises(ValueError, match="remote path shall be absolute"):
            fileloc("a:b.c")


class TestFileLocContext:
    """Test context propagation in Pydantic models."""

    def test_context_in_validation(self):
        """Test that context is passed during validation."""
        from pydantic import BaseModel

        class Config(BaseModel):
            file: FileLoc

        cfg = Config.model_validate(
            {"file": "relative.txt"},
            context={"local_parent_path": "/base"},
        )
        assert "/base" in cfg.file.url

    def test_nested_model_context(self):
        """Test context propagation in nested models."""
        from pydantic import BaseModel

        class Inner(BaseModel):
            file: FileLoc

        class Outer(BaseModel):
            inner: Inner

        cfg = Outer.model_validate(
            {"inner": {"file": "relative.txt"}},
            context={"local_parent_path": "/base"},
        )
        assert "/base" in cfg.inner.file.url

    def test_remote_context_propagation(self):
        """Test remote parent path context propagation."""
        from pydantic import BaseModel

        class Config(BaseModel):
            file: FileLoc

        cfg = Config.model_validate(
            {"file": ("host", "relative.txt")},
            context={"remote_parent_path": "/remote/base"},
        )
        assert "/remote/base" in cfg.file.url
        assert cfg.file.netloc == "host"


class TestFileLocEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_type(self):
        """Test that invalid type raises error."""
        with pytest.raises((TypeError, ValidationError)):
            FileLoc.model_validate(123)

    def test_invalid_tuple_size(self):
        """Test that invalid tuple size raises error."""
        with pytest.raises(ValueError, match="tuple of size"):
            FileLocData((1, 2, 3))  # type: ignore[arg-type]

    def test_empty_string_raises(self):
        """Test that empty string raises error."""
        with pytest.raises(ValueError):
            FileLoc.model_validate("")

    def test_url_with_query_parameters(self):
        """Test URL with query parameters."""
        fl = FileLoc.model_validate("https://example.com/file.txt?key=value")
        assert fl.scheme == "https"
        assert fl.host == "example.com"
        assert "file.txt" in str(fl.path)

    def test_url_with_fragment(self):
        """Test URL with fragment."""
        fl = FileLoc.model_validate("https://example.com/file.txt#section")
        assert fl.scheme == "https"
        assert fl.host == "example.com"

    def test_url_with_port(self):
        """Test URL with port."""
        fl = FileLoc.model_validate("http://example.com:8080/file.txt")
        assert fl.scheme == "http"
        assert fl.host == "example.com"

    def test_url_with_username_password(self):
        """Test URL with username and password."""
        fl = FileLoc.model_validate("http://user:pass@example.com/file.txt")
        assert fl.scheme == "http"
        assert fl.host == "example.com"

    def test_file_url_with_localhost(self):
        """Test file:// URL with localhost."""
        fl = FileLoc.model_validate("file://localhost/data/test.txt")
        assert fl.is_local()
        assert fl.netloc == ""

    def test_path_with_spaces(self):
        """Test path with spaces."""
        fl = FileLoc.model_validate("/data/file with spaces.txt")
        assert "spaces" in str(fl.path)

    def test_path_with_special_chars(self):
        """Test path with special characters."""
        fl = FileLoc.model_validate("/data/file-name_123.txt")
        assert fl.path.name == "file-name_123.txt"


class TestFileLocDataValidation:
    """Test FileLocData validation logic."""

    def test_path_validation_from_string(self):
        """Test that path validator converts string to Path."""
        fld = FileLocData({"path": "/data/test.txt"})
        assert isinstance(fld.path, Path)

    def test_path_validation_keeps_path(self):
        """Test that path validator keeps Path objects."""
        p = Path("/data/test.txt")
        fld = FileLocData({"path": p})
        assert fld.path is p

    def test_model_validator_with_dict_arg(self):
        """Test model_validator with dict argument."""
        fld = FileLocData({"path": "/data/test.txt", "netloc": "host"})
        assert fld.path == Path("/data/test.txt")
        assert fld.netloc == "host"

    def test_local_relative_path_resolution(self):
        """Test local relative path gets resolved."""
        fld = FileLocData("relative.txt")
        assert fld.path_resolved.is_absolute()

    def test_local_absolute_path_unchanged(self):
        """Test local absolute path stays unchanged."""
        fld = FileLocData("/data/test.txt")
        assert str(fld.path_resolved) == "/data/test.txt"

    def test_remote_absolute_path_unchanged(self):
        """Test remote absolute path stays unchanged."""
        fld = FileLocData(("host", "/data/test.txt"))
        assert str(fld.path_resolved) == "/data/test.txt"


class TestFileLocUrlComponents:
    """Test URL component extraction."""

    def test_url_components_http(self):
        """Test all URL components for HTTP URL."""
        url = "http://user:pass@example.com:8080/path/file.txt?key=value#section"
        fl = FileLoc.model_validate(url)
        assert fl.scheme == "http"
        assert fl.host == "example.com"

    def test_url_components_file(self):
        """Test URL components for file:// URL."""
        fl = FileLoc.model_validate("file:///data/test.txt")
        assert fl.scheme == "file"
        assert fl.host == ""

    def test_url_components_remote_file(self):
        """Test URL components for remote file:// URL."""
        fl = FileLoc.model_validate("file://remotehost/data/test.txt")
        assert fl.scheme == "file"
        assert fl.host == "remotehost"


class TestFileLocComparison:
    """Test FileLoc comparison and equality."""

    def test_same_path_creates_equal_urls(self):
        """Test that same path creates equivalent FileLoc."""
        fl1 = FileLoc.model_validate("/data/test.txt")
        fl2 = FileLoc.model_validate("/data/test.txt")
        assert fl1.url == fl2.url

    def test_different_netloc_creates_different_urls(self):
        """Test that different netloc creates different FileLoc."""
        fl1 = FileLoc.model_validate("host1:/data/test.txt")
        fl2 = FileLoc.model_validate("host2:/data/test.txt")
        assert fl1.url != fl2.url


class TestFileLocIntegration:
    """Integration tests for complete workflows."""

    def test_local_file_workflow(self, tmp_path):
        """Test complete workflow with local file."""
        # Create FileLoc
        test_file = tmp_path / "test.txt"
        fl = fileloc(str(test_file))

        # Verify properties
        assert fl.is_local()
        assert not fl.is_remote()
        assert fl.scheme == "file"
        assert fl.host == ""

        # Check rsync format
        rsync_arg = fl.as_rsync_arg()
        assert rsync_arg == str(test_file)

    def test_remote_file_workflow(self):
        """Test complete workflow with remote file."""
        # Create FileLoc
        fl = fileloc("myhost:/data/file.txt")

        # Verify properties
        assert fl.is_remote()
        assert not fl.is_local()
        assert fl.netloc == "myhost"
        assert fl.host == "myhost"
        assert str(fl.path) == "/data/file.txt"

        # Check rsync format
        rsync_arg = fl.as_rsync_arg()
        assert rsync_arg == "myhost:/data/file.txt"

    def test_http_url_workflow(self):
        """Test complete workflow with HTTP URL."""
        # Create FileLoc
        fl = fileloc("https://example.com/data.csv")

        # Verify properties
        assert fl.is_remote()
        assert fl.scheme == "https"
        assert fl.host == "example.com"
        assert "data.csv" in str(fl.path)

    def test_pydantic_integration(self):
        """Test integration with Pydantic models."""
        from pydantic import BaseModel

        class DataConfig(BaseModel):
            input_file: FileLoc
            output_file: FileLoc

        cfg = DataConfig.model_validate(
            {
                "input_file": "/input/data.txt",
                "output_file": "host:/output/result.txt",
            },
        )

        assert cfg.input_file.is_local()
        assert cfg.output_file.is_remote()
        assert cfg.output_file.netloc == "host"

    def test_context_with_pydantic(self):
        """Test context propagation with Pydantic models."""
        from pydantic import BaseModel

        class Config(BaseModel):
            data_dir: FileLoc
            output_file: FileLoc

        cfg = Config.model_validate(
            {
                "data_dir": "data",
                "output_file": "output.txt",
            },
            context={"local_parent_path": "/project"},
        )

        assert "/project" in cfg.data_dir.url
        assert "/project" in cfg.output_file.url
