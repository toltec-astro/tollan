import re

import pytest

from tollan.utils.fileloc import FileLoc


def test_fileloc():
    fl = FileLoc("file:///a.b")

    assert fl.uri == "file:///a.b"
    assert not fl.netloc
    assert fl.path.name == "a.b"
    assert fl.is_local

    fl = FileLoc("file://a/b.c")

    assert fl.uri == "file://a/b.c"
    assert fl.netloc == "a"
    assert fl.path.name == "b.c"
    assert fl.is_remote

    fl = FileLoc("a.b")

    assert fl.uri.endswith("a.b")
    assert not fl.netloc
    assert fl.path.name == "a.b"
    assert fl.is_local

    fl = FileLoc("a:/b.c")

    assert fl.uri == "file://a/b.c"
    assert fl.netloc == "a"
    assert fl.path.name == "b.c"
    assert fl.is_remote

    fl = FileLoc(("a", "b.c"), remote_parent_path="/")
    assert fl.uri == "file://a/b.c"
    assert fl.netloc == "a"
    assert fl.path.name == "b.c"
    assert fl.is_remote

    fl = FileLoc(("", "b.c"), remote_parent_path="/")
    assert re.match(r"file:///.+b\.c", fl.uri)
    assert not fl.netloc
    assert fl.path.name == "b.c"
    assert fl.is_local

    fl = FileLoc(("", "b.c"), remote_parent_path="/", local_parent_path="/")
    assert fl.uri == "file:///b.c"
    assert not fl.netloc
    assert fl.path.name == "b.c"
    assert fl.is_local

    with pytest.raises(ValueError, match="remote path shall be absolute"):
        fl = FileLoc(("a", "b.c"))

    with pytest.raises(ValueError, match="remote path shall be absolute"):
        fl = FileLoc("a:b.c")

    with pytest.raises(ValueError, match="remote path shall be absolute"):
        fl = FileLoc("file://a.c")
