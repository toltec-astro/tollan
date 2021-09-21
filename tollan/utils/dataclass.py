#!/usr/bin/env python
import dataclasses
from functools import lru_cache
from cached_property import cached_property

import schema
import typing_inspect
from wrapt import ObjectProxy
from .fmt import pformat_list
from .misc import odict_from_list


__all__ = ['class_schema', 'DataclassSchema']


MAX_CLASS_SCHEMA_CACHE_SIZE = 1024
"""Cache size for generated schemas."""


def _get_field_default(field):
    """
    Return a Schema default value given a dataclass default value
    """
    default_factory = field.default_factory  # type: ignore
    if default_factory is not dataclasses.MISSING:
        return default_factory
    elif field.default is dataclasses.MISSING:
        return None
    return field.default


def field_to_schema(field):
    metadata = field.metadata or dict()

    if (field.default is not dataclasses.MISSING or
            field.default_factory is not dataclasses.MISSING):
        is_optional = True
    elif typing_inspect.is_optional_type(field.type):
        is_optional = True
    else:
        is_optional = False
    key_kwargs = dict(description=metadata.get('description', None))
    if is_optional:
        key_cls = schema.Optional
        key_kwargs.update(default=_get_field_default(field))
    else:
        key_cls = schema.Literal
    schema_key = key_cls(field.name, **key_kwargs)
    # If the schema value was already defined by the user
    predefined_schema_value = metadata.get("schema", None)
    if predefined_schema_value is not None:
        schema_value = predefined_schema_value
    else:
        # Otherwise we infer schema value from the field type
        schema_value = field.type
    return (schema_key, schema_value)


def class_schema(cls):
    """
    Convert a data class `cls` to `schema.Schema` object.
    """

    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls} is not a dataclass.")
    return _class_schema(cls)


@lru_cache(maxsize=MAX_CLASS_SCHEMA_CACHE_SIZE)
def _class_schema(cls):
    # Copy the schema arguments from Meta
    Meta = getattr(cls, 'Meta', None)
    schema_kwargs = dict()
    if Meta is not None:
        schema_kwargs.update(getattr(Meta, 'schema', dict()))

    fields = dataclasses.fields(cls)

    schema_dict = dict(
        field_to_schema(field) for field in fields if field.init)
    return DataclassSchema(cls, schema.Schema(schema_dict, **schema_kwargs))


class DataclassSchema(ObjectProxy):
    def __init__(self, dataclass_cls, schema):
        super().__init__(schema)
        self._dataclass_cls = dataclass_cls

    @cached_property
    def _fields_dict(self):
        return odict_from_list(
            dataclasses.fields(self._dataclass_cls), key=lambda f: f.name)

    def load(self, d, **kwargs):
        return self._dataclass_cls(**self.validate(d))

    def pformat(self):
        def _pformat_item(k, v):
            # if isinstance(v, (schema.Use)):
            #     func_name = getattr(
            #         v._callable, '__name__', repr(v._callable))
            #     text = f'{func_name}()'
            # else:
            #     text = str(v)
            name = f'{k.schema}'
            # we try to get the dataclass field type here

            def fullname(cls):
                module = cls.__module__
                qualname = cls.__qualname__
                if module is None or module == str.__module__:
                    return qualname
                return f"{module}.{qualname}"
            try:
                type_ = fullname(self._fields_dict[name].type)
            except AttributeError:
                type_ = str(self._fields_dict[name].type)
            text = getattr(k, 'description', None)
            if text is None:
                text = 'N/A'
            if isinstance(k, schema.Optional):
                # text = f'{text} (default={k.default})'
                default_ = k.default
            else:
                default_ = ''
            return (name, type_, default_, text)
        body = pformat_list(
            [
                # ('---', '----', '-------------', '-----------'),
                ('key', 'type', 'default value', 'description'),
                ('---', '----', '-------------', '-----------'),
             ] +
            list(
                _pformat_item(k, v) for k, v in self.schema.items()
                ),
            indent=4)
        cls_desc = self.description or self._dataclass_cls.__doc__
        header = f'{self._dataclass_cls.__name__}'
        return f'{header}:\n  description:\n    {cls_desc}\n  members:{body}'


def add_schema(cls):
    if any(hasattr(cls, a) for a in ('schema', 'todict')):
        raise TypeError(f"`schema` attribute exists on {cls}")
    if dataclasses.is_dataclass(cls):
        cls.schema = class_schema(cls)
        cls.to_dict = dataclasses.asdict
    else:
        raise TypeError(f"cannot create schema from type {cls}")
    return cls
