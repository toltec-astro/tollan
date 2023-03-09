import collections.abc
import os

from ..utils.log import logger
from .models.config_source import ConfigSourceList


class RuntimeContextError(RuntimeError):
    """Error related to runtime context."""

    pass


class RuntimeContext(object):
    """A class to manage runtime context.

    Parameters
    ----------

    config : str, `os.PathLike`, dict, list, optional
        The runtime context config source, can be a file path,  a
        python dict, or a list of config source dict.
    """

    _default_cs_order = 0

    @classmethod
    def _config_to_config_source_list(cls, config):
        if config is None:
            config = dict()
        if isinstance(config, (str, os.PathLike, collections.abc.Mapping)):
            config_source_list = [{"order": cls._default_cs_order, "source": config}]
        elif isinstance(config, collections.abc.Sequence):
            config_source_list = config
        else:
            raise RuntimeContextError(f"invalid config source: {config}.")
        logger.debug(f"load config sources from {len(config_source_list)} items")
        csl = ConfigSourceList.parse_obj(config_source_list)
        logger.debug(f"loaded config sources:\n{csl.yaml()}")
        return csl

    def __init__(self, config):
        self._config_sources = self._config_to_config_source_list(config)


class RuntimeBaseError(RuntimeError):
    """Exception related to Runtime."""

    pass


class RuntimeBase(object):
    """A base class for classes that consume `RuntimeContext`.

    This class acts as a proxy of an underlying `RuntimeContext` object,
    providing a unified interface for subclasses to managed
    specialized config objects constructed from
    the config dict of the runtime context and its the runtime info.

    Parameters
    ----------
    config : `RuntimeContext`, str, `os.PathLike`, dict, list
        The runtime context object, or the config source of it.
    """

    def __init__(self, config):
        if isinstance(config, RuntimeContext):
            rc = config
        else:
            rc = RuntimeContext(config)
        self._rc = rc

    @property
    def rc(self):
        return self._rc

    config_cls = NotImplemented
    """Subclasses implement this to provide specialized config object."""

    def config(self):
        """The config object of :attr:`config_cls` constructed from the
        runtime context config dict.

        The config dict is validated and the constructed object is cached.
        The config object can be updated by using :meth:`RuntimeBase.update`.
        """
        return self.config_cls.from_config_dict(
            self.rc.config,
            # these are passed to the schema validate method
            rootpath=self.rc.rootpath,
            runtime_info=self.rc.runtime_info,
        )
