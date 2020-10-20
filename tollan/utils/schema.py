#! /usr/bin/env python


def create_relpath_validator(rootpath):
    """Return validator to validate a relative path."""

    def validate(p):
        p = rootpath.joinpath(p)
        if p.exists():
            return p
        raise ValueError(f"path does not exist: {p}")

    return validate
