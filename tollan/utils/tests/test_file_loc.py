#! /usr/bin/env python

from ..misc import FileLoc, fileloc
import pytest
import re


def test_file_loc():

    fl = FileLoc(uri='a', netloc='b', path='c')
    assert fl.uri == 'a'
    assert fl.netloc == 'b'
    assert fl.path == 'c'
    assert fl.is_remote

    fl = fileloc('file:///a.b')

    assert fl.uri == 'file:///a.b'
    assert fl.netloc == ''
    assert fl.path.name == 'a.b'
    assert fl.is_local

    fl = fileloc('file://a/b.c')

    assert fl.uri == 'file://a/b.c'
    assert fl.netloc == 'a'
    assert fl.path.name == 'b.c'
    assert fl.is_remote

    fl = fileloc('a.b')

    assert fl.uri.endswith('a.b')
    assert fl.netloc == ''
    assert fl.path.name == 'a.b'
    assert fl.is_local

    fl = fileloc('a:/b.c')

    assert fl.uri == 'file://a/b.c'
    assert fl.netloc == 'a'
    assert fl.path.name == 'b.c'
    assert fl.is_remote

    fl = fileloc(('a', 'b.c'), remote_parent_path='/')
    assert fl.uri == 'file://a/b.c'
    assert fl.netloc == 'a'
    assert fl.path.name == 'b.c'
    assert fl.is_remote

    fl = fileloc(('', 'b.c'), remote_parent_path='/')
    assert re.match(r'file:///.+b\.c', fl.uri)
    assert fl.netloc == ''
    assert fl.path.name == 'b.c'
    assert fl.is_local

    fl = fileloc(('', 'b.c'), remote_parent_path='/', local_parent_path='/')
    assert fl.uri == 'file:///b.c'
    assert fl.netloc == ''
    assert fl.path.name == 'b.c'
    assert fl.is_local

    with pytest.raises(ValueError, match='remote path shall be absolute'):
        fl = fileloc(('a', 'b.c'))

    with pytest.raises(ValueError, match='remote path shall be absolute'):
        fl = fileloc('a:b.c')

    with pytest.raises(ValueError, match='remote path shall be absolute'):
        fl = fileloc('file://a.c')
