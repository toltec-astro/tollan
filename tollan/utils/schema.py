#! /usr/bin/env python

from schema import Schema, Optional


def create_relpath_validator(rootpath):
    """Return validator to validate a relative path."""

    def validate(p):
        p = rootpath.joinpath(p)
        if p.exists():
            return p
        raise ValueError(f"path does not exist: {p}")

    return validate


def make_nested_optional_defaults(s):
    """Return a schema that has optional defaults computed from nested schema.

    All the optionals in the subschemas have to have defaults.

    Parameters
    ----------
    s : `schema.Schema` or dict
        The default schema to render
    """
    if isinstance(s, Schema):
        s = s.schema
    if not isinstance(s, dict):
        raise ValueError("input schema has to be dict.")
    # create default value for nested dict
    # figure out recursion leaf, which is a dict with known default
    # for all keys and no nested dicts

    def _make_default_dict_from_schema_dict(s):
        if not isinstance(s, Schema):
            s = Schema(s)
        if all(not isinstance(v, dict) for v in s.schema.values()):
            return s.validate(dict())
        return {
                k.schema: _make_default_dict_from_schema_dict(v)
                if isinstance(v, dict)
                else k.default for k, v in s.schema.items()}

    d_out = dict()
    for k, v in s.items():
        if not isinstance(k, Optional):
            raise ValueError("input schema key has to be optional")
        if isinstance(v, dict):
            d_out[Optional(
                k.schema,
                default=_make_default_dict_from_schema_dict(v))] = \
                        make_nested_optional_defaults(v)
        else:
            d_out[k] = v
    return Schema(d_out)
