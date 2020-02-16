#! /usr/bin/env python

"""This module defines some helpers for handling env vars."""

import os
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

    def get(self, label):
        if label not in self:
            self.logger.debug(f"env var {label} is not registered")
        result = os.getenv(label, None)
        if result is None or result == '':
            if label in self:
                msg = f"env var {label} ({self[label]}) is not set"
            else:
                msg = f"env var {label} is not set"
            raise ValueError(msg)
        return result

env_registry = EnvRegistry.create()
"""A global environment variable registry instance."""
