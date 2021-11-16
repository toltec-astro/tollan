#! /usr/bin/env python

import os
from .registry import Registry
import pyaml


__all__ = ['EnvRegistry', 'env_registry']


class EnvRegistry(Registry):
    """A registry class to manage env vars and the defaults."""

    _NODEFUALT = "__no_default__"

    def _make_entry(self, name, desc, defval=_NODEFUALT):
        return {'name': name, 'description': desc, 'default': defval}

    def register(self, name, desc, defval=_NODEFUALT):
        """Register an environment variable.

        Parameters
        ----------
        name: str
            The name of the env var.
        desc: str
            The description of the env var.
        defval: str, optional
            The default value.
        """
        if name in self:
            raise KeyError(
                    f"env {name} exists in registry: {self[name]}"
                    )
            # if item != self[label]:
            #     raise KeyError(
            #         f"label={label} exists in registry: {self[label]}")
            # else:
            #     return
        self[name] = self._make_entry(name, desc, defval)
        msg = f"registered env \"{name}\": \"{desc}\""
        if not defval == self._NODEFUALT:
            msg += f' (default={defval})'
        self.logger.debug(msg)

    def get(self, name, *args):
        """Return env var of given name."""
        if name not in self:
            self.logger.warn(f"env var {name} is not registered")
            return os.getenv(name, *args)
        # check default value
        defval = self[name]['default']
        if defval != self._NODEFUALT and len(args) == 0:
            args = (defval, )
        result = os.getenv(name, *args)
        if result == '':
            result = None
        if result is None:
            msg = f"env var {name} ({self[name]['description']}) is not set"

            if len(args) == 0:
                raise ValueError(msg)
            else:
                result = args[0]
                self.logger.debug(msg + f', use default {result}')
        return result

    def summary(self):
        """Return a string as a summary of the env vars."""
        result = {}
        for k, v in self.items():
            result[k] = dict(value=self.get(k), **v)
        return result


env_registry = EnvRegistry.create()
"""A global environment variable registry instance."""


pyaml.add_representer(EnvRegistry, lambda s, d: s.represent_dict(d.summary()))
