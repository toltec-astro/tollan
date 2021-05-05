#! /usr/bin/env python

import inspect
import pyaml
import textwrap
import numpy as np
import math
# from astropy.modeling import Model


__all__ = [
        'pformat_paths', 'pformat_list', 'pformat_dict', 'pformat_obj',
        'pformat_yaml', 'pformat_fancy_index', 'model_to_dict',
        ]


def pformat_paths(paths, sep='\n', relative_to=None, sort=False):
    def fmt_path(p):
        if relative_to is not None:
            p = p.relative_to(relative_to)
        return f'{p!s}'

    def trans(paths):
        if sort:
            return sorted(paths)
        return paths
    return sep.join(trans(fmt_path(p) for p in paths))


def pformat_list(lst, indent, minw=60, max_cell_width=40, fancy=True):
    if not lst or not lst[0]:
        width = None
    else:
        if max_cell_width is None:
            max_cell_width == np.inf
        width = [
                min(max_cell_width, max(len(str(e[i])) for e in lst))
                for i in range(len(lst[0]))]

    def get_cell_width(c):
        return len(c[0]) if len(c) > 0 else 1

    def fmt_elem(e, width=width, fancy=fancy):
        if len(e) == 1:
            return "{}".format(e)
        else:
            if width is not None and (fancy or len(e) == 2):
                if fancy:
                    fmt = '| {} |'.format(
                           ' | '.join("{{:<{}s}}".format(w) for w in width))
                else:  # len(e) == 2
                    fmt = "{{:<{}s}}: {{}}".format(width[0])
            elif len(e) == 2:
                fmt = "{}: {}"
            else:
                fmt = ", ".join("{}" for _ in e)
            if (len(e) == 2) and isinstance(e[1], (float)):
                return fmt.format(str(e[0]), "{:g}".format(e[1]))
            if len(e) == 2 and hasattr(e[1], 'items'):
                return fmt.format(
                        str(e[0]), pformat_dict(e[1], indent=indent + 2))
            # do wrapping
            if max_cell_width > 0 and width is not None:
                cells = [
                        textwrap.wrap(str(ee), width=w)
                        for ee, w in zip(e, width)]
                rows = []
                for i in range(max(len(c) for c in cells)):
                    row = fmt.format(*(
                        c[i] if i < len(c) else ' ' * get_cell_width(c)
                        for c in cells))
                    rows.append(row)
                return '\n'.join(rows)
            return fmt.format(*map(str, e))
    flat = "[{}]".format(
            ', '.join(map(lambda e: fmt_elem(e, width=None), lst)))
    if len(flat) > minw:
        return textwrap.indent(
                ''.join(f'\n{fmt_elem(e)}' for e in lst), ' ' * indent)
        # fmt = "{{:{}s}}{{}}".format(indent)
        # return "\n{}".format(
        #         '\n'.join(fmt.format(" ", fmt_elem(e)) for e in l))
    else:
        return flat


def pformat_dict(d, indent=2, minw=60):
    return pformat_list([e for e in d.items()], indent, fancy=False, minw=minw)


def pformat_obj(m):
    """Return info of python object."""
    result = []
    result.append(str(m))

    if isinstance(m, list):
        return str(m)
    if isinstance(m, dict):
        return pformat_dict(m)

    def iskeep(n):
        if n in ['logger', ]:
            return False
        return not n.startswith('__')

    obj_attrs = [n for n in getattr(m, "__dict__", dict()).keys() if iskeep(n)]

    def format_attrs(attrs):
        result = []
        for n in attrs:
            a = getattr(m, n)
            # d = getattr(a, '__doc__', None) or str(a)
            d = str(a)
            d = d.split('\n')[0]
            if inspect.isfunction(a):
                s = f"{n}{inspect.signature(a)}"
            else:
                s = f"{n}"
            result.append((s, d))
        width = max(len(n) for n, _ in result) + 1
        return result, width

    if obj_attrs:
        fmt_obj_attrs, width = format_attrs(obj_attrs)

        result.append("  attrs:")
        for s, d in fmt_obj_attrs:
            result.append(f"    {{:{width}}}: {{}}".format(s, d))
    return '\n'.join(result)


def pformat_yaml(obj):
    return f"\n{pyaml.dump(obj)}"


def pformat_fancy_index(i):
    if isinstance(i, slice):
        if i.start is None:
            start = ''
        else:
            start = i.start
        if i.stop is None:
            stop = ''
        else:
            stop = i.stop
        result = f'[{start}:{stop}{{}}]'
        if i.step is None or i.step == 1:
            result = result.format('')
        else:
            result = result.format(f':{i.step}')
        return result
    if isinstance(i, np.ndarray):
        return f'<mask {np.sum(i)}/{i.size}>'
    return i


def pformat_bar(
        value, width=40, prefix="", vmin=0., vmax=1., border=True, fill=' ',
        reverse=False):
    """Return a progressbar-like str representation of value.

    Parameters
    ==========
    value : float
        Value to be represented.

    width: int
        Bar width (in character).

    prefix: string
        Text to be prepend to the bar.

    vmin : float
        Minimum value.

    vmax : float
        Maximum value.

    """
    # This code is based on https://gist.github.com/rougier/c0d31f5cbdaac27b876c  # noqa: E501
    # The original license:
    # -----------------------------------------------------------------------------
    # Copyright (c) 2016, Nicolas P. Rougier
    # Distributed under the (new) BSD License.
    # -----------------------------------------------------------------------------

    # Block progression is 1/8
    if reverse:
        # blocks = ["", "▐", "█"]
        blocks = ' ▁▂▃▄▅▆▇█'
    else:
        blocks = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    vmin = vmin or 0.0
    vmax = vmax or 1.0
    if border:
        lsep, rsep = "▏", "▕"
    else:
        lsep, rsep = " ", " "

    # Normalize value
    value = min(max(value, vmin), vmax)
    value = (value - vmin) / (vmax - vmin)
    v = value * width
    x = math.floor(v)  # integer part
    y = v - x          # fractional part
    i = int(round(y * (len(blocks) - 1)))
    bar = "█" * x
    barfrac = blocks[i]
    n = width - x - 1
    nobar = fill * n
    if reverse:
        bar = f'{lsep}{nobar}{barfrac}{bar}{rsep}'
    else:
        bar = f'{lsep}{bar}{barfrac}{nobar}{rsep}'
    return bar


def model_to_dict(m):
    d = dict()
    for s in str(m).split('\n'):
        s = s.strip()
        if s == '':
            continue
        k, v = s.split(':', 1)
        d[k] = v.strip()
    return d


pyaml.add_representer(np.float64, lambda s, d: s.represent_float(d))
pyaml.add_representer(np.float32, lambda s, d: s.represent_float(d))
pyaml.add_representer(np.int32, lambda s, d: s.represent_int(d))
pyaml.add_representer(np.int64, lambda s, d: s.represent_int(d))
pyaml.add_representer(None, lambda s, d: s.represent_str(str(d)))
