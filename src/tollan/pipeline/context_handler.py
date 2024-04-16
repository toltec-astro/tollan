from typing import ClassVar, Generic, TypeVar

from astropy.utils.decorators import classproperty

from ..utils.general import getname

KeyT = TypeVar("KeyT", bound=str)
ContextT = TypeVar("ContextT")


class ContextHandlerMixinBase(Generic[KeyT, ContextT]):
    """A base class to access context stored in dict."""

    _context_handler_context_cls: ClassVar[ContextT]

    @classproperty
    def _context_handler_key(cls) -> KeyT:
        return getname(cls)

    @classmethod
    def set_context(cls, data, context_obj) -> ContextT:
        """Set context."""
        raise NotImplementedError

    @classmethod
    def get_context(cls, data) -> ContextT:
        """Get context."""
        raise NotImplementedError

    @classmethod
    def has_context(cls, data) -> bool:
        """Return True if context exists."""
        raise NotImplementedError

    @classmethod
    def create_context(cls, data, context_data=None) -> ContextT:
        """Create context for data."""
        return cls.set_context(
            data,
            cls._context_handler_context_cls(**(context_data or {})),
        )

    @classmethod
    def get_or_create_context(cls, data, context_data=None) -> ContextT:
        """Get or create context for data."""
        if cls.has_context(data):
            return cls.get_context(data)
        return cls.create_context(data, context_data=context_data)


class DictContextHandlerMixin(ContextHandlerMixinBase[KeyT, ContextT]):
    """A helper class to access context stored in dict."""

    @classmethod
    def get_context_dict(cls, data) -> dict:
        """Get context dict."""
        return data

    @classmethod
    def set_context(cls, data, context_obj: ContextT) -> ContextT:
        """Set context."""
        cls.get_context_dict(data)[cls._context_handler_key] = context_obj
        return context_obj

    @classmethod
    def get_context(cls, data) -> ContextT:
        """Get context."""
        return cls.get_context_dict(data)[cls._context_handler_key]

    @classmethod
    def has_context(cls, data) -> bool:
        """Return True if context exists."""
        return cls._context_handler_key in cls.get_context_dict(data)


class MetadataContextHandlerMixin(DictContextHandlerMixin[KeyT, ContextT]):
    """A helper class to access context stored in metadata dict."""

    @classmethod
    def get_context_dict(cls, data) -> dict:
        """Get context dict."""
        if hasattr(data, "meta"):
            return data.meta
        raise ValueError("data has no metadata.")
