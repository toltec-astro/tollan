"""Type introspection utilities for working with generic types."""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, TypeVar, get_args

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "ensure_cls_attr_from_type_args",
    "get_typing_args",
]


def get_typing_args(  # noqa: C901
    cls: Any,
    max_depth: int | None = 1,
    bound: type | None = None,
    type_filter: type | None = None,
    *,
    unique: bool = False,
) -> Any:
    """Extract typing arguments from a class's generic base classes.

    Recursively traverses the class hierarchy to find all typing arguments
    from Generic base classes. Can filter results by bound (subclass check)
    or type_filter (instance check).

    Parameters
    ----------
    cls : Any
        Class or type construct to extract typing arguments from
    max_depth : int | None, optional
        Maximum depth to traverse the class hierarchy. None means unlimited.
        Default is 1.
    bound : type | None, optional
        Filter results to only include classes that are subclasses of this type
    type_filter : type | None, optional
        Filter results to only include instances of this type
    unique : bool, optional
        If True, expect exactly one result and return it directly (not a list).
        Returns None for generic base classes with unresolved TypeVars.
        Raises ValueError if multiple results found or no results for concrete classes.

    Returns
    -------
    list[Any] | Any | None
        List of typing arguments found, single argument if unique=True,
        or None if unique=True and class is a generic base with TypeVars

    Raises
    ------
    ValueError
        If both bound and type_filter are specified, or if unique=True but
        result is not exactly one element (unless generic base class)

    Examples
    --------
    >>> from typing import Generic, TypeVar
    >>> from pydantic import BaseModel
    >>> T = TypeVar('T')
    >>> class MyHandler(Generic[T]):
    ...     pass
    >>> class MyConfig(BaseModel):
    ...     pass
    >>> class ConcreteHandler(MyHandler[MyConfig]):
    ...     pass
    >>> get_typing_args(ConcreteHandler, bound=BaseModel)  # doctest: +ELLIPSIS
    [<class '...MyConfig'>]
    >>> get_typing_args(  # doctest: +ELLIPSIS
    ...     ConcreteHandler, bound=BaseModel, unique=True
    ... )
    <class '...MyConfig'>

    Notes
    -----
    This function is useful for automatically inferring type parameters from
    Generic base classes, particularly for frameworks that use Generic[T]
    patterns for dependency injection or configuration.
    """

    def _get_args(bases: tuple, depth: int = 0) -> list[Any]:
        """Recursively collect typing arguments from base classes."""
        result: list[Any] = []
        for c in bases:
            # First, try to extract typing args directly
            typing_args = get_args(c)
            if typing_args:
                # This is a parameterized generic (e.g., Base[str])
                # Recurse into the args if within depth
                if max_depth is None or depth < max_depth:
                    result.extend(_get_args(typing_args, depth=depth + 1))
                else:
                    # At max depth, include the args directly
                    result.extend(typing_args)
            elif hasattr(c, "__orig_bases__") and (
                max_depth is None or depth < max_depth
            ):
                # No typing args, but has __orig_bases__ - recurse
                result.extend(_get_args(c.__orig_bases__, depth=depth + 1))
            elif depth > 0:
                # Leaf node at non-root depth - this is a concrete type arg
                result.append(c)
            # else: root level with no args - skip
        return result

    raw_args = _get_args((cls,))

    # Check if this is a generic base class with unresolved type parameters

    has_type_vars = any(isinstance(arg, TypeVar) for arg in raw_args)
    # Always filter out TypeVars - they are placeholders, not concrete types
    args = [arg for arg in raw_args if not isinstance(arg, TypeVar)]

    def _handle_unique(args: list[Any]) -> Any:
        """Handle unique result requirement."""
        if len(args) == 1:
            return args[0]
        # For generic base classes with TypeVars, allow zero filtered results
        if len(args) == 0 and has_type_vars:
            return None
        msg = f"Expected exactly one typing arg, found {len(args)}"
        raise ValueError(msg)

    # If no additional filtering requested, return TypeVar-filtered args
    if bound is None and type_filter is None:
        if unique:
            return _handle_unique(args)
        return args

    # Apply additional bound or type_filter if specified
    # Validate that only one filter is specified
    if bound is not None and type_filter is not None:
        msg = "Only one of 'bound' or 'type_filter' can be specified"
        raise ValueError(msg)

    # Define filter function
    def _issubclass_safe(arg: Any, cls: type) -> bool:
        """Check if arg is a class and subclass of cls."""
        if inspect.isclass(arg):
            return issubclass(arg, cls)
        return False

    def _isinstance_safe(arg: Any, cls: type) -> bool:
        """Check if arg is an instance of cls."""
        return isinstance(arg, cls)

    # Apply appropriate filter
    filter_func: Callable[[Any], bool]
    if bound is not None:
        filter_func = functools.partial(_issubclass_safe, cls=bound)
    elif type_filter is not None:
        filter_func = functools.partial(_isinstance_safe, cls=type_filter)
    else:
        # This should never happen due to earlier validation
        msg = "Either 'bound' or 'type_filter' must be specified"
        raise AssertionError(msg)

    filtered_args = [arg for arg in args if filter_func(arg)]

    # Handle unique result requirement
    if unique:
        return _handle_unique(filtered_args)
    return filtered_args


def ensure_cls_attr_from_type_args(  # noqa: PLR0913
    cls: type,
    attr_name: str,
    max_depth: int = 2,
    bound: type | None = None,
    type_filter: type | None = None,
    *,
    skip_on_exist: bool = True,
    disallow_explicit: bool = True,
) -> None:
    """Ensure a class attribute is set from typing arguments.

    Extract typing arguments from the class's generic base classes and
    set the specified class attribute to the unique matching argument.

    Handles intermediate generic classes gracefully: if the class still has
    unresolved TypeVars (e.g., GenericBase[T] not yet specialized), the
    function silently returns without setting the attribute.

    Parameters
    ----------
    cls : type
        Class to set attribute on
    attr_name : str
        Name of the class attribute to set
    max_depth : int, optional
        Maximum depth to traverse the class hierarchy. Default is 2.
    bound : type | None, optional
        Filter typing arguments to only include subclasses of this type
    type_filter : type | None, optional
        Filter typing arguments to only include instances of this type
    skip_on_exist : bool, optional
        If True, do not overwrite the attribute if it already exists.
    disallow_explicit : bool, optional
        If True, raise TypeError if the attribute is explicitly set on cls
        (not inherited). Forces use of type parameters for consistency.
        Default is True to enforce consistency.

    Raises
    ------
    TypeError
        If disallow_explicit=True and attribute is explicitly set on cls.
    ValueError
        If no matching typing argument is found for a concrete (non-generic) class,
        or if multiple matching arguments are found.

    Notes
    -----
    This function is useful for automatically setting class attributes
    based on Generic[T] type parameters, particularly in frameworks that
    use generics for configuration or dependency injection.

    For intermediate generic classes (with unresolved TypeVars), the function
    gracefully returns without error, allowing subclasses to provide concrete types.

    Examples
    --------
    >>> from typing import Generic, TypeVar
    >>> from pydantic import BaseModel
    >>> T = TypeVar('T')
    >>> class MyHandler(Generic[T]):
    ...     pass
    >>> class MyConfig(BaseModel):
    ...     pass
    >>> class ConcreteHandler(MyHandler[MyConfig]):
    ...     pass
    >>> ensure_cls_attr_from_type_args(
    ...     ConcreteHandler, 'config_model_cls', bound=BaseModel
    ... )
    >>> ConcreteHandler.config_model_cls  # doctest: +ELLIPSIS
    <class '...MyConfig'>
    """
    # Check if attribute is explicitly set on THIS class (not inherited)
    if disallow_explicit and attr_name in cls.__dict__:
        msg = (
            f"{cls.__name__} explicitly sets '{attr_name}'. "
            f"Use type parameter instead: class {cls.__name__}(BaseClass[YourType])"
        )
        raise TypeError(msg)

    attr_value_default = getattr(cls, attr_name, None)
    if attr_value_default is not None and skip_on_exist:
        return

    # Use get_typing_args with unique=True to get exactly one result
    # Returns None for intermediate generic classes with unresolved TypeVars
    attr_value = get_typing_args(
        cls,
        max_depth=max_depth,
        bound=bound,
        type_filter=type_filter,
        unique=True,
    )

    # If None returned, this is an intermediate generic class - skip gracefully
    if attr_value is None:
        return

    # Set the attribute with the resolved type
    setattr(cls, attr_name, attr_value)
