from pathlib import Path

__all__ = ["env_load", "env_dump"]


def env_load(filepath):
    """Load systemd-like environment file into a dict."""
    result = {}
    with Path(filepath).open("r") as fo:
        for ln_ in fo.readlines():
            ln = ln_.strip()
            if not ln or ln.strip().startswith("#"):
                continue
            k, v = map(str.strip, ln.split("=", 1))
            result[k] = v
    return result


def env_dump(_data, _output=None):
    """Dump dict to a systemd-like environment file."""
    return NotImplemented
