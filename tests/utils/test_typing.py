"""Tests for Tollan runtime generic binding resolution."""

from __future__ import annotations

from typing import Literal

import astropy.units as u
import pytest

from tollan.utils.typing import (
    GenericBindingRequirement,
    resolve_concrete_generic_bindings,
    resolve_generic_bindings,
)


class TestResolveGenericBindings:
    """Exercise exact-origin resolution across realistic inheritance graphs."""

    def test_direct_bindings_and_named_access(self):
        class Pair[LeftT, OtherT]:
            pass

        class Concrete(Pair[int, str]):
            pass

        bindings = resolve_generic_bindings(Concrete, Pair)

        assert bindings.origin is Pair
        assert tuple(p.__name__ for p in bindings.type_vars) == (
            "LeftT",
            "OtherT",
        )
        assert bindings.resolved_types == (int, str)
        assert bindings[0] is int
        assert bindings["OtherT"] is str
        assert bindings.is_resolved
        assert bindings.unresolved == ()

    def test_indirect_reordered_and_nested_substitution(self):
        class Pair[LeftT, OtherT]:
            pass

        class Reordered[FirstT, SecondT](Pair[SecondT, list[FirstT]]):
            pass

        class Concrete(Reordered[int, str]):
            pass

        bindings = resolve_generic_bindings(Concrete, Pair)
        assert bindings.resolved_types == (str, list[int])

    def test_partial_specialization_remains_unresolved(self):
        class Pair[LeftT, OtherT]:
            pass

        class Partial[ValueT](Pair[int, ValueT]):
            pass

        partial = resolve_generic_bindings(Partial, Pair)
        assert partial.resolved_types[0] is int
        assert partial.unresolved == ("OtherT",)
        assert not partial.is_resolved

        class Concrete(Partial[str]):
            pass

        assert resolve_generic_bindings(Concrete, Pair).resolved_types == (
            int,
            str,
        )

    def test_unrelated_generic_arguments_are_ignored(self):
        class Target[ValueT]:
            pass

        class Unrelated[ValueT]:
            pass

        class Mixed(Unrelated[str], Target[int]):
            pass

        assert resolve_generic_bindings(Mixed, Target).resolved_types == (int,)

    def test_literal_is_preserved_as_the_exact_argument(self):
        class Keyed[KeyT]:
            pass

        class Concrete(Keyed[Literal["science"]]):
            pass

        binding = resolve_generic_bindings(Concrete, Keyed)["KeyT"]
        assert binding == Literal["science"]

    def test_pep696_default_is_used_for_bare_inheritance(self):
        class Defaulted[ValueT = int]:
            pass

        class Concrete(Defaulted):
            pass

        assert resolve_generic_bindings(Concrete, Defaulted).resolved_types == (int,)

    def test_bare_required_parameters_remain_unresolved(self):
        class Required[ValueT]:
            pass

        class Concrete(Required):
            pass

        bindings = resolve_generic_bindings(Concrete, Required)
        assert bindings.unresolved == ("ValueT",)

    def test_consistent_diamond_is_accepted(self):
        class Target[ValueT]:
            pass

        class Left(Target[int]):
            pass

        class Right(Target[int]):
            pass

        class Diamond(Left, Right):
            pass

        assert resolve_generic_bindings(Diamond, Target).resolved_types == (int,)

    def test_conflicting_diamond_is_rejected(self):
        class Target[ValueT]:
            pass

        class Left(Target[int]):
            pass

        class Right(Target[str]):
            pass

        class Diamond(Left, Right):  # ty: ignore[invalid-generic-class]
            pass

        with pytest.raises(TypeError, match="Conflicting .*Target bindings"):
            resolve_generic_bindings(Diamond, Target)

    def test_invalid_target_and_type_variable_name_errors(self):
        class Target[ValueT]:
            pass

        class Other:
            pass

        with pytest.raises(TypeError, match="is not a subclass"):
            resolve_generic_bindings(Other, Target)

        bindings = resolve_generic_bindings(Target, Target)
        with pytest.raises(KeyError, match="no type variable"):
            bindings["MissingT"]


class TestResolveConcreteGenericBindings:
    """Exercise the shared class-creation policy used by Tollan consumers."""

    def test_concrete_binding_is_validated(self):
        class RuntimeBase:
            pass

        class Target[ValueT]:
            pass

        class RuntimeValue(RuntimeBase):
            pass

        class Concrete(Target[RuntimeValue]):
            pass

        bindings = resolve_concrete_generic_bindings(
            Concrete,
            Target,
            ValueT=GenericBindingRequirement("runtime_value", RuntimeBase),
        )

        assert bindings is not None
        assert bindings["ValueT"] is RuntimeValue

    def test_intermediate_defers_but_bare_subclass_fails(self):
        class Target[ValueT]:
            pass

        class Intermediate[ValueT](Target[ValueT]):
            pass

        requirement = GenericBindingRequirement("runtime_value")
        assert (
            resolve_concrete_generic_bindings(
                Intermediate,
                Target,
                ValueT=requirement,
            )
            is None
        )

        class Bare(Intermediate):
            pass

        with pytest.raises(TypeError, match="must bind Target's type variables"):
            resolve_concrete_generic_bindings(
                Bare,
                Target,
                ValueT=requirement,
            )

    def test_explicit_runtime_attribute_and_invalid_bound_fail(self):
        class RuntimeBase:
            pass

        class Target[ValueT]:
            pass

        class Explicit(Target[RuntimeBase]):
            runtime_value = RuntimeBase

        requirement = GenericBindingRequirement("runtime_value", RuntimeBase)
        with pytest.raises(TypeError, match="explicitly sets 'runtime_value'"):
            resolve_concrete_generic_bindings(
                Explicit,
                Target,
                ValueT=requirement,
            )

        class Invalid(Target[int]):
            pass

        with pytest.raises(TypeError, match="must bind ValueT"):
            resolve_concrete_generic_bindings(
                Invalid,
                Target,
                ValueT=requirement,
            )


class TestQuantityPhysicalType:
    """Test physical-type extraction from Quantity annotations."""

    def test_unit_physical_type(self):
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        assert get_physical_type_from_quantity_type(u.Quantity[u.m]) == "length"
        assert get_physical_type_from_quantity_type(u.Quantity[u.s]) == "time"

    def test_string_physical_type(self):
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        assert get_physical_type_from_quantity_type(u.Quantity["length"]) == "length"
        assert get_physical_type_from_quantity_type(u.Quantity["time"]) == "time"

    def test_derived_units(self):
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        assert get_physical_type_from_quantity_type(u.Quantity[u.m / u.s]) == "speed"
        assert (
            get_physical_type_from_quantity_type(u.Quantity[u.kg * u.m / u.s**2])
            == "force"
        )

    def test_invalid_quantity_type(self):
        from tollan.config.types.quantity import get_physical_type_from_quantity_type

        assert get_physical_type_from_quantity_type(int) is None
        assert get_physical_type_from_quantity_type(str) is None
