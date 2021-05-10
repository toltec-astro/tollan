#! /usr/bin/env python

import socket
import os
import sys
import appdirs
from pathlib import Path


__all__ = ['get_hostname', 'touch_file']


def get_hostname():
    """Same as the shell command `hostname`"""
    return socket.gethostname()


def touch_file(out_file):
    """Same as the shell command `touch`."""

    with open(out_file, 'a'):
        os.utime(out_file, None)


def get_or_create_dir(dirpath, on_exist=None, on_create=None):
    """Ensure the `dirpath` exists.

    Parameters
    ==========
    dirpath : `pathlib.Path`, str
        The path of the directory.
    on_exist : callable, optional
        If set, called if `dirpath` exists already.
    on_create : callable, optional
        If set, called if `dirpath` is created.
    """
    dirpath = Path(dirpath)
    if dirpath.exists():
        if on_exist is not None:
            on_exist(dirpath)
        return dirpath
    os.makedirs(dirpath)
    if on_create is not None:
        on_create(dirpath)
    return dirpath


def get_user_data_dir():
    """Return the directory for saving user data."""
    return Path(appdirs.user_data_dir('tollan', 'toltec'))


def parse_systemd_envfile(filepath):
    """Parse systemd environment file into a dict.

    """
    result = dict()
    with open(filepath, 'r') as fo:
        for ln in fo.readlines():
            ln = ln.strip()
            if ln == '' or ln.strip().startswith("#"):
                continue
            k, v = map(str.strip, ln.split('=', 1))
            result[k] = v
    return result


def find_parent_package_path(filepath, package_name, add_to_sys_path=False):
    """Return the path of parent package of `package_name` of `filepath`.

    This works by traversing up the file tree and looking for the first
    path which has the sub-path matches `package_name`.
    """

    filepath = Path(filepath).resolve()
    subpath = ''
    while not subpath.startswith(package_name):
        subpath = f'{filepath.name}.{subpath}'
        if filepath == filepath.parent:
            raise ValueError("unable to locate package in file tree.")
        filepath = filepath.parent
    if add_to_sys_path:
        sys.path.insert(0, filepath.as_posix())
    return filepath
