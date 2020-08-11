#! /usr/bin/env python


from collections import OrderedDict
from .log import get_logger
import wrapt
import copy


__all__ = ['register_to', 'Registry']


class RegistryMixin(object):
    logger = get_logger()

    def register(self, label, item):
        if label in self:
            raise KeyError(
                f"label={label} exists in registry: {self[label]}")
        self[label] = item
        self.logger.debug(
                f"registered {item} as \"{label}\"")


def register_to(registry, key):
    """Register the decorated item with key."""

    def decorator(cls):
        if callable(key):
            _key = key(cls)
        else:
            _key = key
        registry.register(_key, cls)
        return cls

    return decorator


def register_method_to(registry, key):

    register_to_decorator = register_to(registry, key)

    class decorator(object):

        def __init__(self, func):

            register_to_decorator(func)
            self.func = func

        def __get__(self, obj, cls):

            return self.func

        @property
        def __isabstractmethod__(self):
            return getattr(self.func, "__isabstractmethod__", False)

    return decorator


class Registry(wrapt.ObjectProxy, RegistryMixin):

    @classmethod
    def create(cls, container_cls=OrderedDict):
        return cls(container_cls())

    def __copy__(self):
        return Registry(copy.copy(self.__wrapped__))
