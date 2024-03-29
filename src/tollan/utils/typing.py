import functools
import inspect
from typing import get_args

import astropy.units as u
from typing_extensions import assert_never


def get_typing_args(  # noqa: C901
    cls,
    max_depth=1,
    bound=None,
    type=None,
    unique=False,
):
    """Return a list of typing args from cls."""

    def _get_args(bases, depth=0):
        result = []
        for c in bases:
            if max_depth is None or depth < max_depth:
                if hasattr(c, "__orig_bases__"):
                    result.extend(_get_args(c.__orig_bases__, depth=depth + 1))
                else:
                    cs = _get_args(get_args(c), depth=depth + 1)
                    if cs:
                        result.extend(cs)
                    elif depth > 0:
                        result.append(c)
                    else:
                        pass
            elif depth > 0:
                result.append(c)
            else:
                pass
        return result

    args = _get_args([cls])
    if bound is None and type is None:
        return args
    if bound is not None and type is not None:
        raise ValueError("only one of bound or type can be specified.")

    def _issubclass(arg, cls):
        if inspect.isclass(arg):
            return issubclass(arg, cls)
        return False

    def _isinstance(arg, cls):
        return isinstance(arg, cls)

    if bound is not None:
        ff = functools.partial(_issubclass, cls=bound)
    else:
        ff = functools.partial(_isinstance, cls=type)

    args = [arg for arg in args if ff(arg)]
    if unique:
        if len(args) == 1:
            return args[0]
        raise ValueError("ambiguous result found.")
    return args


def get_physical_type_from_quantity_type(cls):
    """Return physical type from quantity type alias, if any."""
    args = get_typing_args(cls, type=u.PhysicalType | u.UnitBase)
    for arg in args:
        if isinstance(arg, u.PhysicalType):
            return arg
        if isinstance(arg, u.UnitBase):
            return arg.physical_type
        assert_never()
    return None
