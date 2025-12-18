"""Context handler mixins for managing context data in pipeline objects.

This module provides mixin classes for storing and retrieving context objects
in dictionaries or metadata attributes. Context handlers enable type-safe
access to configuration and state data attached to pipeline objects.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any, ClassVar, cast

from pydantic import BaseModel

from ..utils.py import getname

__all__ = [
    "ContextHandlerMixinBase",
    "DictContextHandlerMixin",
    "MetadataContextHandlerMixin",
]


class ContextHandlerMixinBase[KeyT: str, ContextT]:
    """Base class for managing context objects in data containers.

    Provides a framework for storing, retrieving, and managing typed context
    objects. Subclasses must implement the storage mechanism (dict, metadata, etc.).
    """

    _context_handler_context_cls: ClassVar[type]

    @classmethod
    def _context_handler_key(cls) -> KeyT:
        """Get the storage key for this handler's context."""
        return cast("KeyT", getname(cls))

    @classmethod
    def set_context(cls, data: Any, context_obj: ContextT) -> ContextT:
        """Set context object for data.

        Parameters
        ----------
        data : Any
            Data container to store context in
        context_obj : ContextT
            Context object to store

        Returns
        -------
        ContextT
            The stored context object
        """
        raise NotImplementedError

    @classmethod
    def get_context(cls, data: Any) -> ContextT:
        """Get context object from data.

        Parameters
        ----------
        data : Any
            Data container to retrieve context from

        Returns
        -------
        ContextT
            The stored context object
        """
        raise NotImplementedError

    @classmethod
    def has_context(cls, data: Any) -> bool:
        """Check if context exists in data.

        Parameters
        ----------
        data : Any
            Data container to check

        Returns
        -------
        bool
            True if context exists, False otherwise
        """
        raise NotImplementedError

    @classmethod
    def create_context(
        cls,
        data: Any,
        context_data: dict[str, Any] | None = None,
    ) -> ContextT:
        """Create new context for data.

        Parameters
        ----------
        data : Any
            Data container to store context in
        context_data : dict[str, Any], optional
            Initialization data for context object

        Returns
        -------
        ContextT
            The created context object
        """
        return cls.set_context(
            data,
            cls._context_handler_context_cls(**(context_data or {})),
        )

    @classmethod
    def get_or_create_context(
        cls,
        data: Any,
        context_data: dict[str, Any] | None = None,
    ) -> ContextT:
        """Get existing context or create new one if missing.

        Parameters
        ----------
        data : Any
            Data container to retrieve or store context in
        context_data : dict[str, Any], optional
            Initialization data for context object if creating new

        Returns
        -------
        ContextT
            The context object (existing or newly created)
        """
        if cls.has_context(data):
            return cls.get_context(data)
        return cls.create_context(data, context_data=context_data)


class DictContextHandlerMixin[KeyT: str, ContextT](
    ContextHandlerMixinBase[KeyT, ContextT],
):
    """A helper class to access context stored in dict."""

    @classmethod
    def get_context_dict(cls, data: Any) -> dict[KeyT, ContextT]:
        """Get dictionary storing contexts.

        Parameters
        ----------
        data : Any
            Data object (should be a dict)

        Returns
        -------
        dict[KeyT, ContextT]
            Dictionary containing contexts keyed by handler name
        """
        return data

    @classmethod
    def set_context(cls, data: Any, context_obj: ContextT) -> ContextT:
        """Set context in dictionary.

        Parameters
        ----------
        data : Any
            Dictionary to store context in
        context_obj : ContextT
            Context object to store

        Returns
        -------
        ContextT
            The stored context object
        """
        cls.get_context_dict(data)[cls._context_handler_key()] = context_obj
        return context_obj

    @classmethod
    def get_context(cls, data: Any) -> ContextT:
        """Get context from dictionary.

        Validates and converts raw context data to proper type if needed.

        Parameters
        ----------
        data : Any
            Dictionary containing context

        Returns
        -------
        ContextT
            The context object (validated and typed)
        """
        context_data = cls.get_context_dict(data)[cls._context_handler_key()]
        ctx_cls = cls._context_handler_context_cls
        if isinstance(context_data, ctx_cls):
            return context_data
        if issubclass(ctx_cls, BaseModel):
            context_obj = ctx_cls.model_validate(context_data)
        elif is_dataclass(ctx_cls):
            context_obj = ctx_cls(**context_data)  # ty:ignore[invalid-argument-type]
        else:
            context_obj = ctx_cls(context_data)
        context_obj = cast("ContextT", context_obj)
        cls.get_context_dict(data)[cls._context_handler_key()] = context_obj
        return context_obj

    @classmethod
    def has_context(cls, data: Any) -> bool:
        """Check if context key exists in dictionary.

        Parameters
        ----------
        data : Any
            Dictionary to check

        Returns
        -------
        bool
            True if context key exists, False otherwise
        """
        return cls._context_handler_key() in cls.get_context_dict(data)


class MetadataContextHandlerMixin[KeyT: str, ContextT](
    DictContextHandlerMixin[KeyT, ContextT],
):
    """A helper class to access context stored in metadata dict."""

    @classmethod
    def get_context_dict(cls, data: Any) -> dict[KeyT, ContextT]:
        """Get metadata dictionary storing contexts.

        Parameters
        ----------
        data : Any
            Data object with .meta attribute

        Returns
        -------
        dict[KeyT, ContextT]
            Metadata dictionary containing contexts

        Raises
        ------
        ValueError
            If data object has no .meta attribute
        """
        if hasattr(data, "meta"):
            return data.meta
        msg = "data has no .meta attribute"
        raise ValueError(msg)
