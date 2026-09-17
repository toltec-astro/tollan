"""Handlers for environment values stored in runtime configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, RootModel

from .handler import ConfigHandler
from .runtime_context import RuntimeContext
from .sources import ENV_NAMESPACE_DEFAULT

if TYPE_CHECKING:
    from .runtime_context import RuntimeConfig
    from .sources import DictConfigT

__all__ = ["EnvConfig", "EnvHandler"]


class EnvConfig(RootModel[dict[str, Annotated[str, BeforeValidator(str)]]]):
    """Environment mapping with string keys and values converted using ``str``.

    The mapping is available as ``root``. Values from YAML or CLI overrides
    use Python string conversion, e.g. ``8000`` becomes ``"8000"`` and
    ``True`` becomes ``"True"``.
    """

    model_config = ConfigDict(frozen=True, strict=True)


class EnvHandler(ConfigHandler[EnvConfig, RuntimeContext[Any]]):
    """Capture environment settings without modifying the process environment.

    Construct directly to read the default environment namespace. For a custom
    namespace, request the handler from ``RuntimeContext.from_cli`` or
    ``from_cli_ctx`` with ``return_env_handler=True``.

    Like other config handlers, this captures settings at construction. Use
    ``recreate()`` to read updated runtime settings, or ``temporary_config()``
    to create a separately configured handler.

    Examples
    --------
    >>> from tollan.config import RuntimeContext
    >>> rc, handler = RuntimeContext.from_cli(
    ...     cli_args=["--_env.PORT", "8000"], return_env_handler=True
    ... )
    >>> handler.as_environ()
    {'PORT': '8000'}
    """

    _namespace: ClassVar[str] = ENV_NAMESPACE_DEFAULT

    @classmethod
    def prepare_config_data(cls, runtime_config: RuntimeConfig) -> DictConfigT:
        """Extract the environment namespace, using an empty mapping if absent."""
        if cls._namespace in type(runtime_config).model_fields:
            return getattr(runtime_config, cls._namespace)
        return (runtime_config.model_extra or {}).get(cls._namespace, {})

    @classmethod
    def prepare_runtime_config_data(cls, config_data: DictConfigT) -> DictConfigT:
        """Wrap an environment patch under this handler's namespace."""
        return {cls._namespace: config_data}

    def as_environ(self) -> dict[str, str]:
        """Return a fresh environment dict, without inheriting or setting variables.

        Merge with ``os.environ`` explicitly when passing it to a subprocess.
        The merge order determines which values take precedence.
        """
        return self.config.root.copy()


def _make_env_handler(
    runtime_context: RuntimeContext[Any], namespace: str
) -> EnvHandler:
    """Construct a handler whose recreation and patches retain the namespace."""
    if namespace == ENV_NAMESPACE_DEFAULT:
        return EnvHandler(runtime_context)

    # The namespace is class-bound so inherited recreation/temporary-config
    # methods preserve it. Do not retain these per-call classes in the registry.
    class EnvHandlerBound(EnvHandler, register_with_runtime_context=False):
        _namespace = namespace

    return EnvHandlerBound(runtime_context)
