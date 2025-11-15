"""Configuration system using ConfigSourceList and RuntimeContext.

This module provides a modern configuration system with two main components.

Architecture::

    RuntimeContext (entry point) - Manages config lifecycle and context
        ↓ owns
    ConfigSourceList (config loader) - Loads and merges config from multiple sources
        ↓ consumed by
    ConfigHandler (domain adapter) - Validates and caches domain-specific config

Sources Supported
-----------------
- YAML files (including conditional loading with enable_if)
- Dictionary sources
- Environment files (.env)
- Nested config source lists

Basic Example:
    >>> from pathlib import Path
    >>> from tollan.config import RuntimeContext
    >>> rc = RuntimeContext(
    ...     config_sources=[
    ...         {"format": "dict", "source": {"app": "test"}, "order": 0},
    ...         {
    ...             "format": "dict",
    ...             "source": {"debug": True},
    ...             "order": 1,
    ...             "enable_if": "env == 'production'",
    ...         }
    ...     ]
    ... )
    >>> config_dict = rc.config_dict  # Merged config dict (cached property)
    >>> config = rc.config  # Validated RuntimeConfig model (cached property)
    >>> runtime_info = rc.runtime_info  # Auto-detected runtime info

CLI Example (with factory method):
    >>> from pathlib import Path
    >>> from tollan.config import RuntimeContext
    >>> # CLI parsing example (doesn't require files)
    >>> rc = RuntimeContext.from_cli(cli_args=["--debug", "true", "--port", "8080"])
    >>> rc.config_dict['debug']
    True

Context Override Example:
    >>> with rc.set_context({"env": "production"}):
    ...     prod_config = rc.config_dict

Domain-Specific Example (with ConfigHandler):
    >>> # See ConfigHandler documentation for complete example
    ... # doctest: +SKIP
"""

from __future__ import annotations

from .base import FrozenBaseModel
from .runtime_context import RuntimeConfig, RuntimeContext
from .runtime_info import RuntimeInfo

__all__ = [
    "ConfigHandler",
    "FrozenBaseModel",
    "RuntimeConfig",
    "RuntimeContext",
    "RuntimeInfo",
    "SubConfigKeyTransformer",
]


# this has to be imported after RuntimeContext.
from .handler import ConfigHandler, SubConfigKeyTransformer
