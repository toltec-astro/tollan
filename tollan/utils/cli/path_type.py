#! /usr/bin/env python


from pathlib import Path
from argparse import ArgumentTypeError


__all__ = ['PathType']


class PathType(object):
    """
    A class that facilitates path-like argument for `~argparse.Argument`

    Parameters
    ----------
    exists : bool or None
        If True or False, ensure the path exists or not exists.

    type_ : str, callable, optional
        The type of the path, can be one of "file", "dir", "symlink" or
        a predicate function. It set, the type is enforced.
    """

    def __init__(self, exists=True, type_='file'):

        if not ((type_ in ('file', 'dir', 'symlink', None))
                or callable(type_)):
            raise ValueError('invalid value for "type_"')
        self._exists = exists
        self._type = type_

    def __call__(self, arg):
        p = Path(arg)
        e = p.exists()

        if self._exists is not None:
            if self._exists and not e:
                raise ArgumentTypeError(f"path does not exist: {p}")

            if (not self._exists) and e:
                raise ArgumentTypeError(f"path exists: {p}")
        if not p.exists():
            return p
        if self._type is None:
            pass
        elif self._type == 'file' and not p.is_file():
            raise ArgumentTypeError(f"path is not a file: {p}")
        elif self._type == 'symlink' and not p.is_symlink():
            raise ArgumentTypeError(f"path is not a symlink: {p}")
        elif self._type == 'dir' and not p.is_dir():
            raise ArgumentTypeError(f"path is not a dir: {p}")
        elif callable(self._type) and not self._type(arg):
            raise ArgumentTypeError(f"path not valid: {arg}")
        else:
            d = p.resolve(strict=False).parent
            if not d.is_dir():
                raise ArgumentTypeError(f"parent path is not a dir: {p}")
            elif not d.exists():
                raise ArgumentTypeError(f"parent dir does not exist: {p}")
        return p
