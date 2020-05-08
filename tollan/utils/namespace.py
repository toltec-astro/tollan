#! /usr/bin/env python

from types import SimpleNamespace
from . import rupdate, getobj
from copy import copy


__all__ = [
        'NamespaceNotFoundError', 'NamespaceTypeError',
        'Namespace',
        'object_from_dict', 'dict_from_object']


class NamespaceNotFoundError(Exception):
    pass


class NamespaceTypeError(Exception):
    pass


class NamespaceMixin(object):
    """A mixin class that allows converting object to and from dict.
    """

    def _namespace_to_dict_op(self):
        return copy(self.__dict__)

    _namespace_to_dict_schema = None

    _namespace_from_dict_op = staticmethod(copy)

    _namespace_from_dict_schema = None

    _namespace_type_key = '__class__'

    @classmethod
    def _namespace_check_type(cls, ns_type):
        return cls is ns_type

    def to_dict(self, **kwargs):
        """Return the attributes dict.

        This is different from `~tollan.utils.namespace.dict_from_object` in
        that it uses the class attributes as the defaults, thus could behave
        differently if called from subclasses.

        .. note::

            The class attribute settings may be overriden by the content of
            `kwargs`.

        Parameters
        ----------
        **kwargs
            keyword arguments passed to
            `~tollan.utils.namespace.dict_from_object`
        """
        return dict_from_object(
                self,
                keys_attr=None,
                schema_attr='_namespace_to_dict_schema',
                **kwargs)

    @classmethod
    def from_dict(cls, d, **kwargs):
        """Construct a `~tollan.utils.namespace.Namespace` instance from dict.

        This is different from `~tollan.utils.namespace.object_from_dict` in
        that it uses the class attributes as the defaults, thus could behave
        differently if called from subclasses.

        .. note::

            The class attribute settings may be overriden by the content of
            `d` and `kwargs`.

        Parameters
        ----------
        *args
            A list of dicts.
        **kwargs
            Additional keyword arguments that get updated to the dict.
        """
        return object_from_dict(
                d,
                _namespace_from_dict_op=cls._namespace_from_dict_op,
                _namespace_from_dict_schema=cls._namespace_from_dict_schema,
                _namespace_type_key=cls._namespace_type_key,
                _namespace_check_type=cls._namespace_check_type,
                _namespace_default_type=cls,
                **kwargs)


class Namespace(NamespaceMixin, SimpleNamespace):
    """A convenient class that manages a set of attributes."""
    pass


def dict_from_object(
        obj,
        keys_attr='__all__',
        schema_attr='_namespace_to_dict_schema',
        schema=None,
        keys=None,
        to_dict_op=None):
    """Return a dict composed from object's attributes.

    All attributes are filtered by and in the order of `keys_attr`,
    `schema_attr`, `schema`, and `keys`.

    Parameters
    ----------
    keys_attr : str or None
        The attribute name that contains a list of attributes to keep as keys.

    schema_attr : str or None
        The attribute name that specifies a schema to filter the attributes.

    schema : `~schema.Schema` or None
        The schema to filter the attributes.

    keys : list of str
        A list of attribuate names to keep as keys.

    to_dict_op : callable or None
        The operator to create the raw dict from obj. If None, the `dir` based
        dict is returned.
    """
    # these are keys that should not care by users.
    ignored_keys = [
            '__builtins__', '__cached__',
            '__loader__', '__spec__',
            ]
    if to_dict_op is None:
        def to_dict_op(o):
            return {k: getattr(o, k) for k in dir(o)
                    if k not in ignored_keys}
    d = to_dict_op(obj)
    # get from keys_attr
    ks = d.keys()
    if keys_attr is not None and hasattr(obj, keys_attr):
        ks = getattr(obj, keys_attr)
    d = {k: getattr(obj, k) for k in ks}
    # look for schema from schema and schema attr
    if schema is None:
        schema = getattr(obj, schema_attr, None)
    if schema is not None:
        d = schema.validate(d)
    # finally select the keys
    if keys is not None:
        d = {k: d[k] for k in keys if k in d}
    return d


def object_from_dict(
        d,
        _namespace_from_dict_op=NamespaceMixin._namespace_from_dict_op,
        _namespace_from_dict_schema=NamespaceMixin._namespace_from_dict_schema,
        _namespace_type_key=NamespaceMixin._namespace_type_key,
        _namespace_check_type=None,
        _namespace_default_type=None,
        **kwargs):
    """Construct a `~tollan.utils.namespace.Namespace` object from dict.

    Parameters
    ----------
    _namespace_from_dict_op : callable
        If set, this is applied to the input dict `d` before the `kwargs` get
        merged to it. Default is "copy".
    _namespace_from_dict_schema : `~schema.Schema` or None
        If set, it is used to filter the dict before instantiate the instance.
    _namespace_type_key : str
        This is passed to `~tollan.utils.getobj` to get the type of the object
        to be constructed. `~tollan.utils.namespace.NamespaceNotFoundError` is
        raised if no valid namespace type is found.
    _namespace_check_type : callable or None
        If set, it is evaluated with the found namespace type for validation.
        `~tollan.utils.namespace.NamespaceTypeError` is raised if the
        validation fails.
    _namespace_default_type : `NamespaceMixin` subclass.
        If set, this is assumed when the namespace type cannot be inferred
        from `_namespace_type_key`.
    **kwargs
        Additional keyword arguments that get updated to the dict.
    """
    # the below merges the kwargs to d
    # notes that we also add some of the _namespace_*  kwargs
    # so that these get stored into the created object.
    d = _prepare_dict(
            d,
            _namespace_from_dict_op=_namespace_from_dict_op,
            _namespace_from_dict_schema=_namespace_from_dict_schema,
            _namespace_type_key=_namespace_type_key,
            _namespace_check_type=_namespace_check_type,
            **kwargs)
    # this has to go before the schema validation
    # in case the type key get pruned.
    # type_key and check_type is already in d
    ns_type = _get_namespace_type(
            d, _namespace_default_type=_namespace_default_type)
    # apply the schema
    schema = d.get('_namespace_from_dict_schema', _namespace_from_dict_schema)
    if schema is None:
        # use the found type schema if no schema is set.
        schema = ns_type._namespace_from_dict_schema
    if schema is not None:
        d = schema.validate(d)
    return ns_type(**d)


def _prepare_dict(d, _namespace_from_dict_op=copy, **kwargs):
    """Return a dict composed from `d` and `kwargs`.

    .. note::
        The keyword argument `_namespace_from_dict_op` is is only used
        when "_namespace_from_dict_op" is not defined in `d`.

    Parameters
    ----------
    _namespace_from_dict_op : callable
        The function to apply to `d` before merging.
    """
    _namespace_from_dict_op = d.get(
            '_namespace_from_dict_op', _namespace_from_dict_op)
    d = _namespace_from_dict_op(d)
    rupdate(d, kwargs)
    return d


def _get_namespace_type(
        d,
        _namespace_type_key='__class__',
        _namespace_check_type=None,
        _namespace_default_type=None):
    """Return the namespace type to use.

    .. note::
        The keyword argument `_namespace_default_type` is only used
        when "_namespace_type_key" is not defined in `d`.

    Parameters
    ----------
    _namespace_type_key : str
        This is passed to `~tollan.utils.getobj` to get the type of the object
        to be constructed. `~tollan.utils.namespace.NamespaceNotFoundError` is
        raised if no valid namespace type is found.
    _namespace_check_type : callable or None
        If set, it is evaluated with the found namespace type for validation.
        `~tollan.utils.namespace.NamespaceTypeError` is raised if the
        validation fails.
    _namespace_default_type : `NamespaceMixin` subclass.
        If set, this is assumed when the namespace type cannot be inferred
        from `_namespace_type_key`.
    """
    type_key = d.get('_namespace_type_key', _namespace_type_key)
    if type_key not in d and _namespace_default_type is None:
            raise NamespaceNotFoundError(
                f"unable to get namespace type: missing type_key {type_key}")
    ns_type = d.get(type_key, _namespace_default_type)
    if isinstance(ns_type, str):
        try:
            ns_type = getobj(ns_type)
        except Exception:
            raise NamespaceNotFoundError(
                    f'unable to import namespace type {ns_type}')
    check_type = d.get('_namespace_check_type', _namespace_check_type)
    if check_type is not None and (not check_type(ns_type)):
        raise NamespaceTypeError(f"invalid namespace type {ns_type}")
    else:
        if not issubclass(ns_type, NamespaceMixin):
            raise NamespaceNotFoundError(
                    f'(sub-) class of NamespaceMixin expected, got {ns_type}')
    return ns_type
