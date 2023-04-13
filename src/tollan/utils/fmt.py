import numpy as np
import pyaml

__all__ = ["pformat_yaml"]

pyaml.add_representer(np.float64, lambda s, d: s.represent_float(d))
pyaml.add_representer(np.float32, lambda s, d: s.represent_float(d))
pyaml.add_representer(np.int32, lambda s, d: s.represent_int(d))
pyaml.add_representer(np.int64, lambda s, d: s.represent_int(d))
pyaml.add_representer(None, lambda s, d: s.represent_str(str(d)))


def pformat_yaml(obj):
    """Return object as pretty-formatted string."""
    if hasattr(obj, "__wrapped__"):
        # unwrap if has wrapped interface
        obj = obj.__wrapped__
    return f"\n{pyaml.dump(obj)}"


def pformat_fancy_index(arg):
    """Return pretty-formated index or slice."""
    if isinstance(arg, slice):
        start = "" if arg.start is None else arg.start
        stop = "" if arg.stop is None else arg.stop
        result = f"[{start}:{stop}{{}}]"
        if arg.step is None or arg.step == 1:
            result = result.format("")
        else:
            result = result.format(f":{arg.step}")
        return result
    if isinstance(arg, np.ndarray):
        return f"<mask {np.sum(arg)}/{arg.size}>"
    return arg
