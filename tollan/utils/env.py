#! /usr/bin/env python

"""This module defines some helpers for handling env vars."""

from .registry import Registry


class EnvRegistry(Registry):
    """A registry class that holds env vars with their short descriptions."""

    def register(self, label, item):
        if label in self:
            if item != self[label]:
                raise KeyError(
                    f"label={label} exists in registry: {self[label]}")
            else:
                return
        self[label] = item
        self.logger.debug(
                f"registered env \"{label}\": \"{item}\"")

    def make_doc(self):
        print(self)


env_registry = EnvRegistry.create()
"""A global environment variable registry instance."""
