#! /usr/bin/env python

import socket
import os
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
            if ln.strip().startswith("#"):
                continue
            k, v = map(str.strip, ln.split('=', 1))
            result[k] = v
    return result
