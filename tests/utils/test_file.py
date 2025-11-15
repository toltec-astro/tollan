"""Tests for tollan.utils.file module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tollan.utils.file import (
    ensure_abspath,
    ensure_path_parent_exists,
    ensure_readable_fileobj,
    get_or_create_dir,
    resolve_symlink,
    touch_file,
)


class TestEnsureAbspath:
    """Test ensure_abspath function."""

    def test_ensure_abspath_with_relative_path(self):
        """Test converting relative path to absolute."""
        result = ensure_abspath(".")
        assert result.is_absolute()
        assert isinstance(result, Path)

    def test_ensure_abspath_with_tilde(self):
        """Test expanding tilde in path."""
        result = ensure_abspath("~/test")
        assert result.is_absolute()
        assert "~" not in str(result)

    def test_ensure_abspath_with_absolute_path(self, tmp_path):
        """Test that absolute path remains absolute."""
        result = ensure_abspath(str(tmp_path))
        assert result == tmp_path

    def test_ensure_abspath_with_path_object(self):
        """Test with Path object input."""
        result = ensure_abspath(Path())
        assert result.is_absolute()


class TestResolveSymlink:
    """Test resolve_symlink function."""

    def test_resolve_symlink_no_link(self):
        """Test resolve_symlink with non-symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.touch()
            result = resolve_symlink(filepath)
            assert result == filepath

    def test_resolve_symlink_single_level(self):
        """Test resolving single-level symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target.txt"
            target.touch()
            link = Path(tmpdir) / "link.txt"
            link.symlink_to(target)

            result = resolve_symlink(link)
            assert result == target

    def test_resolve_symlink_multi_level(self):
        """Test resolving multi-level symlink chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target.txt"
            target.touch()
            link1 = Path(tmpdir) / "link1.txt"
            link1.symlink_to(target)
            link2 = Path(tmpdir) / "link2.txt"
            link2.symlink_to(link1)

            result = resolve_symlink(link2)
            assert result == target

    def test_resolve_symlink_max_iterations(self):
        """Test max iterations limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a long chain
            target = Path(tmpdir) / "target.txt"
            target.touch()
            prev = target
            for i in range(10):
                link = Path(tmpdir) / f"link{i}.txt"
                link.symlink_to(prev)
                prev = link

            # Should raise with n_iter_max=3
            with pytest.raises(ValueError, match="maximum iteration exceeded"):
                resolve_symlink(prev, n_iter_max=3)

    def test_resolve_symlink_match_parent(self):
        """Test stopping resolution when parent matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            target = subdir / "target.txt"
            target.touch()
            link = Path(tmpdir) / "link.txt"
            link.symlink_to(target)

            result = resolve_symlink(link, match_parent=subdir)
            assert result == target


class TestEnsureReadableFileobj:
    """Test ensure_readable_fileobj function."""

    def test_ensure_readable_fileobj_with_path(self):
        """Test with file path."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            with ensure_readable_fileobj(temp_path) as f:
                content = f.read()  # type: ignore[union-attr]
                assert "test content" in content
        finally:
            Path(temp_path).unlink()

    def test_ensure_readable_fileobj_with_fileobj(self):
        """Test with already-opened file object."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("test content")
            f.seek(0)
            temp_path = f.name

        try:
            with (
                Path(temp_path).open() as f,
                ensure_readable_fileobj(f) as f2,
            ):
                assert f2 is f
                content = f2.read()  # type: ignore[union-attr]
                assert "test content" in content
        finally:
            Path(temp_path).unlink()

    def test_ensure_readable_fileobj_with_directory_raises(self):
        """Test that directory raises ValueError."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            pytest.raises(ValueError, match="cannot create readable context"),
            ensure_readable_fileobj(tmpdir),
        ):
            pass


class TestTouchFile:
    """Test touch_file function."""

    def test_touch_file_creates_new(self):
        """Test that touch_file creates new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "new_file.txt"
            assert not filepath.exists()
            touch_file(filepath)
            assert filepath.exists()

    def test_touch_file_updates_existing(self):
        """Test that touch_file updates modification time."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "existing.txt"
            filepath.touch()
            old_mtime = filepath.stat().st_mtime

            # Wait a bit and touch again
            import time

            time.sleep(0.01)
            touch_file(filepath)
            new_mtime = filepath.stat().st_mtime
            assert new_mtime >= old_mtime


class TestGetOrCreateDir:
    """Test get_or_create_dir function."""

    def test_get_or_create_dir_creates_new(self):
        """Test creating new directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            newdir = Path(tmpdir) / "new_directory"
            assert not newdir.exists()
            result = get_or_create_dir(newdir)
            assert newdir.exists()
            assert newdir.is_dir()
            assert result == newdir

    def test_get_or_create_dir_exists(self):
        """Test with existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_or_create_dir(tmpdir)
            assert result == Path(tmpdir)

    def test_get_or_create_dir_with_on_create(self):
        """Test on_create callback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            newdir = Path(tmpdir) / "new_directory"
            created = []

            def on_create(path):
                created.append(path)

            get_or_create_dir(newdir, on_create=on_create)
            assert len(created) == 1
            assert created[0] == newdir

    def test_get_or_create_dir_with_on_exist(self):
        """Test on_exist callback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            existed = []

            def on_exist(path):
                existed.append(path)

            get_or_create_dir(tmpdir, on_exist=on_exist)
            assert len(existed) == 1
            assert existed[0] == Path(tmpdir)

    def test_get_or_create_dir_creates_parents(self):
        """Test that parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "parent" / "child" / "grandchild"
            assert not nested.exists()
            _result = get_or_create_dir(nested)
            assert nested.exists()
            assert nested.is_dir()


class TestEnsurePathParentExists:
    """Test ensure_path_parent_exists function."""

    def test_ensure_path_parent_exists_creates_parent(self):
        """Test creating parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "file.txt"
            assert not filepath.parent.exists()
            result = ensure_path_parent_exists(filepath)
            assert filepath.parent.exists()
            assert result == filepath

    def test_ensure_path_parent_exists_with_existing_parent(self):
        """Test with existing parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "file.txt"
            result = ensure_path_parent_exists(filepath)
            assert result == filepath

    def test_ensure_path_parent_exists_raises_for_directory(self):
        """Test that directory path raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dirpath = Path(tmpdir) / "subdir"
            dirpath.mkdir()
            with pytest.raises(ValueError, match="invalid path type"):
                ensure_path_parent_exists(dirpath)
