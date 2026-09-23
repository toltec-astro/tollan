"""Runtime resolution for user-defined generic class bindings."""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass
from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Any, TypeVar, get_args, get_origin

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "GenericBindingRequirement",
    "GenericBindings",
    "resolve_concrete_generic_bindings",
    "resolve_generic_bindings",
]


@dataclass(frozen=True)
class GenericBindingRequirement:
    """Runtime policy for one origin type variable used by a framework class.

    ``runtime_attr`` names the class attribute derived from the resolved type. It
    is used to reject a second, conflicting source of truth. ``bound`` enables
    the common requirement that the resolved type be a subclass of a runtime
    base.
    """

    runtime_attr: str
    bound: type | None = None


@dataclass(frozen=True)
class GenericBindings:
    """Resolved types for the variables declared by one generic origin.

    ``type_vars`` and ``resolved_types`` retain the order declared by ``origin``.
    A resolved type may still contain a type variable when the inspected class
    is an intermediate generic class.
    """

    origin: type
    type_vars: tuple[Any, ...]
    resolved_types: tuple[Any, ...]

    def __getitem__(self, key: int | str) -> Any:
        """Return a resolved type by position or origin type-variable name."""
        if isinstance(key, int):
            return self.resolved_types[key]
        for type_var, resolved_type in zip(
            self.type_vars,
            self.resolved_types,
            strict=True,
        ):
            if type_var.__name__ == key:
                return resolved_type
        msg = f"{self.origin.__qualname__} has no type variable {key!r}"
        raise KeyError(msg)

    @property
    def unresolved(self) -> tuple[str, ...]:
        """Names of bindings that still contain runtime type variables."""
        return tuple(
            type_var.__name__
            for type_var, resolved_type in zip(
                self.type_vars,
                self.resolved_types,
                strict=True,
            )
            if _contains_type_parameter(resolved_type)
        )

    @property
    def is_resolved(self) -> bool:
        """Whether every origin type variable has a concrete resolved type."""
        return not self.unresolved


def _declared_type_vars(cls: type) -> tuple[Any, ...]:
    """Return the PEP 695 type variables declared directly by ``cls``."""
    return tuple(getattr(cls, "__type_params__", ()))


def _generic_origin_and_args(value: Any) -> tuple[Any, tuple[Any, ...]]:
    """Inspect a standard type expression or Pydantic model specialization."""
    if isinstance(value, type) and issubclass(value, BaseModel):
        # Pydantic subscriptions produce classes, not typing aliases. Read only
        # this class's metadata: inherited metadata can describe a different base.
        metadata = value.__dict__.get("__pydantic_generic_metadata__")
        if metadata is not None and metadata["origin"] is not None:
            return metadata["origin"], metadata["args"]
    return get_origin(value), get_args(value)


def _contains_type_parameter(value: Any) -> bool:
    if isinstance(value, TypeVar):
        return True
    if isinstance(value, list | tuple):
        return any(_contains_type_parameter(item) for item in value)
    _, parts = _generic_origin_and_args(value)
    return any(_contains_type_parameter(item) for item in parts)


def _substitute(value: Any, substitutions: dict[Any, Any]) -> Any:
    """Substitute type variables recursively through a type expression."""
    if isinstance(value, TypeVar):
        replacement = substitutions.get(value, value)
        return (
            value if replacement is value else _substitute(replacement, substitutions)
        )
    if isinstance(value, list | tuple):
        resolved_items = (_substitute(item, substitutions) for item in value)
        if isinstance(value, list):
            return list(resolved_items)
        return tuple(resolved_items)

    _, parts = _generic_origin_and_args(value)
    if not parts:
        return value
    resolved_parts = tuple(_substitute(item, substitutions) for item in parts)
    if resolved_parts == parts:
        return value
    return _rebuild_type_expression(value, parts, resolved_parts)


def _rebuild_type_expression(
    value: Any,
    original_parts: tuple[Any, ...],
    resolved: tuple[Any, ...],
) -> Any:
    """Rebuild a parameterized expression after TypeVar substitution."""
    origin, _ = _generic_origin_and_args(value)
    if origin is typing.Annotated:
        return typing.Annotated[resolved[0], *original_parts[1:]]
    if origin is typing.Literal:
        return typing.Literal[resolved]
    if origin in (typing.Union, types.UnionType):
        return reduce(or_, resolved)
    try:
        item = resolved[0] if len(resolved) == 1 else resolved
        return origin[item]
    except TypeError as e:
        msg = f"Unable to substitute type variables in {value!r}"
        raise TypeError(msg) from e


def _substitutions_for_base(
    origin: type,
    supplied_types: tuple[Any, ...],
    inherited_substitutions: dict[Any, Any],
) -> dict[Any, Any]:
    """Build substitutions for one original base expression."""
    type_vars = _declared_type_vars(origin)
    if not type_vars:
        return {}
    if len(supplied_types) > len(type_vars):
        msg = (
            f"{origin.__qualname__} declares {len(type_vars)} type variables "
            f"but its base expression supplies {len(supplied_types)} types"
        )
        raise TypeError(msg)

    substitutions: dict[Any, Any] = {}
    for type_var, supplied_type in zip(type_vars, supplied_types, strict=False):
        substitutions[type_var] = _substitute(
            supplied_type,
            inherited_substitutions,
        )

    for type_var in type_vars[len(supplied_types) :]:
        default = getattr(type_var, "__default__", typing.NoDefault)
        if default is typing.NoDefault:
            substitutions[type_var] = type_var
        else:
            substitutions[type_var] = _substitute(
                default,
                inherited_substitutions | substitutions,
            )
    return substitutions


def _initial_substitutions(cls: type) -> dict[Any, Any]:
    """Represent a generic class itself, including PEP 696 defaults."""
    return _substitutions_for_base(cls, (), {})


def _walk_generic_paths(
    current: type,
    target_origin: type,
    origin_type_vars: tuple[Any, ...],
    substitutions: dict[Any, Any],
    path: tuple[str, ...],
) -> Iterator[tuple[tuple[Any, ...], tuple[str, ...]]]:
    """Yield the target bindings reached by every inheritance path."""
    current_origin, current_args = _generic_origin_and_args(current)
    if current_origin is not None:
        yield from _walk_generic_paths(
            current_origin,
            target_origin,
            origin_type_vars,
            _substitutions_for_base(current_origin, current_args, substitutions),
            (*path, current_origin.__qualname__),
        )
        return

    if current is target_origin:
        resolved_types = tuple(
            _substitute(
                substitutions.get(type_var, type_var),
                substitutions,
            )
            for type_var in origin_type_vars
        )
        yield resolved_types, path
        return

    for base_expression in types.get_original_bases(current):
        base_origin, base_args = _generic_origin_and_args(base_expression)
        base_origin = base_origin or base_expression
        if not isinstance(base_origin, type) or base_origin is typing.Generic:
            continue
        try:
            reaches_target = issubclass(base_origin, target_origin)
        except TypeError:
            reaches_target = False
        if not reaches_target:
            continue
        base_substitutions = _substitutions_for_base(
            base_origin,
            base_args,
            substitutions,
        )
        yield from _walk_generic_paths(
            base_origin,
            target_origin,
            origin_type_vars,
            base_substitutions,
            (*path, base_origin.__qualname__),
        )


def resolve_generic_bindings(cls: type, origin: type) -> GenericBindings:
    """Resolve ``origin`` type variables as inherited by ``cls``.

    Unlike a recursive ``get_args`` scan, resolution is tied to one exact
    generic origin. Type variables are substituted at every inheritance edge,
    unrelated generic bases are ignored, and conflicting diamond paths fail
    explicitly.

    An intermediate generic class returns bindings containing unresolved type
    variables. Consumers can use :attr:`GenericBindings.is_resolved` to
    defer materializing runtime class attributes until specialization.

    Pydantic generic models are supported. For class-creation hooks on models,
    call this from ``__pydantic_init_subclass__`` rather than ``__init_subclass__``.
    """
    if not isinstance(cls, type) or not isinstance(origin, type):
        msg = "resolve_generic_bindings expects class objects"
        raise TypeError(msg)
    if not issubclass(cls, origin):
        msg = f"{cls.__qualname__} is not a subclass of {origin.__qualname__}"
        raise TypeError(msg)

    origin_type_vars = _declared_type_vars(origin)
    if not origin_type_vars:
        msg = f"{origin.__qualname__} does not declare PEP 695 type variables"
        raise TypeError(msg)

    resolved_paths = list(
        _walk_generic_paths(
            cls,
            origin,
            origin_type_vars,
            _initial_substitutions(cls),
            (cls.__qualname__,),
        ),
    )
    if not resolved_paths:
        msg = (
            f"Unable to find generic base {origin.__qualname__} from {cls.__qualname__}"
        )
        raise TypeError(msg)

    resolved_types, first_path = resolved_paths[0]
    for other_resolved_types, other_path in resolved_paths[1:]:
        if other_resolved_types != resolved_types:
            msg = (
                f"Conflicting {origin.__qualname__} bindings for "
                f"{cls.__qualname__}: {resolved_types!r} via "
                f"{' -> '.join(first_path)}; {other_resolved_types!r} via "
                f"{' -> '.join(other_path)}"
            )
            raise TypeError(msg)

    return GenericBindings(
        origin=origin,
        type_vars=origin_type_vars,
        resolved_types=resolved_types,
    )


def resolve_concrete_generic_bindings(
    cls: type,
    origin: type,
    /,
    **requirements: GenericBindingRequirement,
) -> GenericBindings | None:
    """Apply the common class-creation policy to generic bindings.

    The low-level resolver only describes the inheritance graph. Framework
    consumers additionally need the same three rules: a runtime class
    attribute cannot be set explicitly, an intermediate generic class may
    defer materialization, and a concrete resolved type may need a class bound.

    ``None`` means that one of the requested type variables remains unresolved on
    a genuinely generic intermediate class. A bare concrete subclass with the
    same unresolved type variable is rejected.
    """
    if not requirements:
        msg = "At least one generic binding requirement is needed"
        raise ValueError(msg)

    bindings = resolve_generic_bindings(cls, origin)
    for parameter_name, requirement in requirements.items():
        # Validate the type-variable name even when the class also violates the
        # runtime-attribute rule, so a misspelled requirement cannot hide.
        bindings[parameter_name]
        if requirement.runtime_attr in cls.__dict__:
            msg = (
                f"{cls.__name__} explicitly sets "
                f"{requirement.runtime_attr!r}. Use {origin.__name__}'s "
                f"type variables as the single source of truth"
            )
            raise TypeError(msg)

    unresolved = tuple(name for name in bindings.unresolved if name in requirements)
    if unresolved:
        # A Pydantic partial specialization is itself a class, created before
        # the user's intermediate subclass declares its own type variables.
        if _declared_type_vars(cls) or _generic_origin_and_args(cls)[0] is not None:
            return None
        msg = (
            f"{cls.__name__} must bind {origin.__name__}'s type variables: "
            f"{', '.join(unresolved)}"
        )
        raise TypeError(msg)

    for parameter_name, requirement in requirements.items():
        resolved_type = bindings[parameter_name]
        bound = requirement.bound
        if bound is not None and (
            not isinstance(resolved_type, type) or not issubclass(resolved_type, bound)
        ):
            msg = (
                f"{cls.__name__} must bind {parameter_name} to a "
                f"{bound.__name__} subclass, got {resolved_type!r}"
            )
            raise TypeError(msg)
    return bindings
