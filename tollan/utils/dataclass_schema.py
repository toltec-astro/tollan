#!/usr/bin/env python
import dataclasses
from functools import lru_cache
from cached_property import cached_property

import schema
import inspect
import typing_inspect
import collections.abc
import functools
from .fmt import pformat_list
from .misc import odict_from_list
from .namespace import Namespace


__all__ = [
    'DataclassSchemaOptional', 'DataclassSchema',
    'class_schema', 'add_schema', 'DataclassNamespace']


MAX_CLASS_SCHEMA_CACHE_SIZE = 1024
"""Cache size for generated schemas."""


class DataclassSchemaOptional(schema.Optional):
    """A helper class to expand Optional default for data class members.
    """

    def __init__(self, *args, **kwargs):
        dataclass_cls = kwargs.pop('dataclass_cls', None)
        self._dataclass_cls = dataclass_cls
        super().__init__(*args, **kwargs)

    @property
    def dataclass_cls(self):
        """Return the dataclass this schema is associated with."""
        return self._dataclass_cls

    @property
    def default(self):
        """The default value.

        It detects the `create_instance` argument in the validate call
        and return dataclass instance if True.
        """
        d = self._default_value
        # when the field is not of dataclass type
        if self.dataclass_cls is None:
            # the callable needs to be wrapped to it takes the
            # create_instance argument but does not do any thing
            # this simplifies the signature
            if callable(d):
                return lambda **k: d()
            return d
        # this is the case with dataclass_cls
        if isinstance(d, collections.abc.Mapping):
            # wrap this in a callable to handle "create_instance"
            def wrapped(**kwargs):
                create_instance = kwargs.get('create_instance', False)
                if create_instance:
                    return self._dataclass_cls.from_dict(d)
                # this needs to be validated, as the default can
                # omit any optional value
                import pdb
                pdb.set_trace()
                return self._dataclass_cls.schema.validate(d)
            return wrapped
        if callable(d):
            # assume kwargs are already handled by the callable
            return d
        # just do nothing, to allow for stuff like None
        return d

    @default.setter
    def default(self, value):
        self._default_value = value


class DataclassSchema(schema.Schema):
    """A schema subclass for schema generated from dataclass.
    """

    def __init__(self, *args, **kwargs):
        dataclass_cls = kwargs.pop('dataclass_cls', None)
        # if dataclass_cls is None:
        #     raise ValueError("dataclass_cls is required")
        super().__init__(*args, **kwargs)
        self._dataclass_cls = dataclass_cls

    @property
    def dataclass_cls(self):
        """Return the dataclass this schema is associated with."""
        return self._dataclass_cls

    def validate(self, data, create_instance=False):
        """Validate `data`, optionally create the dataclass instance.

        Parameters
        ----------

        data : dict
            The dict to validate

        create_instance: bool
            If True, return the instance created from validated dict.
        """
        # validate the data. Note that the create_instance is propagated
        # down to any nested DataclassSchema instance's validate method.
        data = super().validate(data, create_instance=create_instance)
        if self.dataclass_cls is not None and create_instance:
            return self.dataclass_cls(**data)
        return data

    def load(self, data):
        """Return the instance of :attr:`dataclass_cls` created from `data`
        after validation."""
        return self.validate(data, create_instance=True)

    def default_factory(self, default_value):
        """Return a callable suitable to be used as default_factory.

        By default this is to create instance, so that when used as
        field default factory, no argument is required.
        """
        def factory(**kwargs):
            create_instance = kwargs.get('create_instance', True)
            if create_instance:
                return self.dataclass_cls.from_dict(default_value)
            # when not creating, we'll return the default value as is.
            return default_value
        return factory

    @cached_property
    def _fields_dict(self):
        """The fields of the `dataclass_cls`, keyed by the field names."""
        return odict_from_list(
            dataclasses.fields(self.dataclass_cls), key=lambda f: f.name)

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
                fields_dict = self._fields_dict
                try:
                    type_ = fullname(fields_dict[name].type)
                except AttributeError:
                    type_ = str(fields_dict[name].type)
            except TypeError:
                if isinstance(v, DataclassSchema):
                    type_ = fullname(v.dataclass_cls)
                else:
                    type_ = fullname(v if inspect.isclass(v) else type(v))
            text = getattr(k, 'description', None)
            if text is None:
                text = 'N/A'
            if isinstance(k, schema.Optional):
                # text = f'{text} (default={k.default})'
                default_ = getattr(k, 'default', '')
                # expand callable default
                if callable(default_):
                    if isinstance(k, DataclassSchemaOptional):
                        default_ = default_(create_instance=False)
                    else:
                        default_ = default_()
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
        cls_desc = self.description or self.dataclass_cls.__doc__
        header = self.name or self.dataclass_cls.__name__
        return f'{header}:\n  description:\n    {cls_desc}\n  members:{body}'


def _get_field_default(field):
    """
    Return a Schema default value given a dataclass default value
    """
    default_factory = field.default_factory  # type: ignore
    if default_factory is not dataclasses.MISSING:
        if dataclasses.is_dataclass(default_factory):
            # the default factory needs to be replaced
            # with the default_factory type
            return default_factory.default_factory(dict())
        return default_factory
    elif field.default is dataclasses.MISSING:
        return None
    return field.default


def field_to_schema(field):
    """Return the schema (key, value) pair for given dataclass field."""
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
        key_cls = DataclassSchemaOptional
        if dataclasses.is_dataclass(field.type):
            # for nested dataclass, we pass to the optional subclass
            key_kwargs.update(dataclass_cls=field.type)
        else:
            # regular optional type
            # we also need the spacial subclass of optional
            # to handle more gracefully the default factory
            # of the other fileds
            pass
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
        if dataclasses.is_dataclass(field.type):
            schema_value = getattr(field.type, 'schema', field.type)
        else:
            schema_value = field.type
    return (schema_key, schema_value)


def class_schema(dataclass_cls):
    """
    Create `schema.Schema` from `dataclass_cls`.
    """

    if not dataclasses.is_dataclass(dataclass_cls):
        raise TypeError(f"{dataclass_cls} is not a dataclass.")
    return _class_schema(dataclass_cls)


@lru_cache(maxsize=MAX_CLASS_SCHEMA_CACHE_SIZE)
def _class_schema(dataclass_cls):
    # Copy the schema arguments from Meta
    Meta = getattr(dataclass_cls, 'Meta', None)
    schema_kwargs = dict(dataclass_cls=dataclass_cls)
    if Meta is not None:
        schema_kwargs.update(getattr(Meta, 'schema', dict()))
    # set the schema kwargs with some sensible default
    schema_kwargs.setdefault('description', dataclass_cls.__doc__)
    schema_kwargs.setdefault('name', dataclass_cls.__qualname__)

    fields = dataclasses.fields(dataclass_cls)

    schema_dict = dict(
        field_to_schema(field) for field in fields if field.init)
    return DataclassSchema(schema_dict, **schema_kwargs)


def add_schema(cls):
    """A decorator to add schema and related methods to dataclass `cls`."""
    if any(hasattr(cls, a) for a in (
            'schema', 'optional', 'default_factory', 'to_dict', 'from_dict')):
        raise TypeError(f"conflicted attribute exists on {cls}")
    if dataclasses.is_dataclass(cls):
        cls.schema = class_schema(cls)
        cls.optional = functools.partial(
            DataclassSchemaOptional, dataclass_cls=cls)
        cls.default_factory = cls.schema.default_factory
        cls.to_dict = dataclasses.asdict
        cls.from_dict = cls.schema.load
    else:
        raise TypeError(f"cannot create schema from type {cls}")
    return cls


class DataclassNamespace(Namespace):
    """A subclass of `tollan.utils.namespace.Namespace`
    that support dataclass type members.
    """
    _namespace_validate_kwargs = {'create_instance': True}

    def __init_subclass__(cls):
        """This provides the schema attribute with same behavior
        as the dataclass decorated with `add_schema`.
        """
        cls.schema = DataclassSchema(
            cls._namespace_from_dict_schema.schema,
            dataclass_cls=cls)
