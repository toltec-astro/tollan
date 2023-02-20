#! /usr/bin/env python


__all__ = ["env_load", "env_dump"]


def env_load(filepath):
    """Load systemd-like environment file into a dict."""
    result = dict()
    with open(filepath, "r") as fo:
        for ln in fo.readlines():
            ln = ln.strip()
            if ln == "" or ln.strip().startswith("#"):
                continue
            k, v = map(str.strip, ln.split("=", 1))
            result[k] = v
    return result


def env_dump(data, output=None):
    """Dump dict to a systemd-like environment file."""
    return NotImplemented
