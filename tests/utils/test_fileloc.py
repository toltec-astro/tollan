import re

import pytest

from tollan.utils.fileloc import FileLoc, FileLocData, fileloc


def test_fileloc_data():
    fld = FileLocData("file:///a.b")
    assert fld.url_resolved.unicode_string() == "file:///a.b"
    assert not fld.netloc_resolved
    assert fld.path_resolved.name == "a.b"

    fld2 = FileLocData(fld)
    assert fld2.url_resolved.unicode_string() == "file:///a.b"
    assert not fld2.netloc_resolved
    assert fld2.path_resolved.name == "a.b"

    # context
    fld = FileLocData(("a", "b.c"), remote_parent_path="/remote")
    assert fld.url_resolved.unicode_string() == "file://a/remote/b.c"
    assert fld.netloc_resolved == fld.netloc == "a"
    assert fld.path_resolved.name == "b.c"

    fld2 = FileLocData(fld)
    assert fld2.url_resolved.unicode_string() == "file://a/remote/b.c"

    # new context on FileLocData instance should fail
    with pytest.raises(ValueError, match="remote_parent_path not allowed"):
        fld3 = FileLocData(fld, remote_parent_path="/remote2")


def test_fileloc():
    # use single argument and FileLoc class
    fl = FileLoc("file:///a.b")

    assert fl.url == "file:///a.b"
    assert not fl.netloc
    assert fl.path.name == "a.b"
    assert fl.is_local()

    fl = FileLoc("file://a/b.c")

    assert fl.url == "file://a/b.c"
    assert fl.netloc == "a"
    assert fl.path.name == "b.c"
    assert fl.is_remote()

    fl = FileLoc("a.b")

    assert fl.url.endswith("a.b")
    assert not fl.netloc
    assert fl.path.name == "a.b"
    assert fl.is_local()

    fl = FileLoc("a:/b.c")

    assert fl.url == "file://a/b.c"
    assert fl.netloc == "a"
    assert fl.path.name == "b.c"
    assert fl.is_remote()

    # validate FileLoc
    fl2 = FileLoc(fl)
    assert fl2.url == "file://a/b.c"
    assert fl2.netloc == "a"
    assert fl2.path.name == "b.c"
    assert fl2.is_remote()

    # fileloc helper to pass the context
    fl = fileloc(("a", "b.c"), remote_parent_path="/")
    assert fl.url == "file://a/b.c"
    assert fl.netloc == "a"
    assert fl.path.name == "b.c"
    assert fl.is_remote()

    fl = fileloc(("", "b.c"), remote_parent_path="/")
    assert re.match(r"file:///.+b\.c", fl.url)
    assert fl.netloc == ""
    assert fl.path.name == "b.c"
    assert fl.is_local()

    fl = fileloc(
        ("localhost", "b.c"), remote_parent_path="/", local_parent_path="/local"
    )
    assert fl.url == "file:///local/b.c"
    assert fl.netloc == ""
    assert fl.path.name == "b.c"
    assert fl.is_local()

    # revalidate
    # default is false
    fl2 = fileloc(fl, local_parent_path="/parent")
    assert fl2.url == fl.url

    fl2 = fileloc(fl, local_parent_path="/parent", revalidate=True)
    assert fl2.url == "file:///parent/b.c"

    with pytest.raises(ValueError, match="remote path shall be absolute"):
        fl = fileloc(("a", "b.c"))

    with pytest.raises(ValueError, match="remote path shall be absolute"):
        fl = fileloc("a:b.c")

    # TODO, this is tricky, and may need some special logic to
    # avoid resolving to remote host root /
    # with pytest.raises(ValueError, match="remote path shall be absolute"):
    #    fl = fileloc("file://a.c")
