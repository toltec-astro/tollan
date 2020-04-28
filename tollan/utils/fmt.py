#! /usr/bin/env python

import inspect
import pyaml
import textwrap
import numpy as np


__all__ = [
        'pformat_paths', 'pformat_list', 'pformat_dict', 'pformat_obj',
        'pformat_yaml', 'pformat_fancy_index'
        ]


def pformat_paths(paths, sep='\n'):
    return sep.join(f'{p!s}' for p in paths)


def pformat_list(l, indent, minw=60, max_cell_width=40, fancy=True):
    if not l or not l[0]:
        width = None
    else:
        if max_cell_width is None:
            max_cell_width == np.inf
        width = [
                min(max_cell_width, max(len(str(e[i])) for e in l))
                for i in range(len(l[0]))]

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
                        c[i] if i < len(c) else ' ' * len(c[0])
                        for c in cells))
                    rows.append(row)
                return '\n'.join(rows)
            return fmt.format(*map(str, e))
    flat = "[{}]".format(
            ', '.join(map(lambda e: fmt_elem(e, width=None), l)))
    if len(flat) > minw:
        return textwrap.indent(
                ''.join(f'\n{fmt_elem(e)}' for e in l), ' ' * indent)
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
    return i


pyaml.add_representer(None, lambda s, d: s.represent_str(str(d)))