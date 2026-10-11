"""Tests for Tollan runtime generic binding resolution."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, Union

import astropy.units as u
import pytest
from pydantic import BaseModel

from tollan.utils.typing import (
    GenericBindingRequirement,
    get_annotation_types,
    resolve_concrete_generic_bindings,
    resolve_generic_bindings,
)


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (int, {int}),
        (int | None, {int, type(None)}),
        (Union[int, str], {int, str}),  # noqa: UP007 -- legacy union inspection
        (Annotated[int | None, "unitless"], {int, type(None)}),
        (Literal["csv", "json", 1, True], {str, int, bool}),
        (list[int], {list[int]}),
        (Any, {Any}),
    ],
)
def test_annotation_value_types(annotation, expected):
    assert get_annotation_types(annotation) == expected


def test_annotation_aliases_and_recursive_branch():
    type Choice = Literal["csv", "json"]
    type OptionalChoice = Annotated[Choice | None, "format"]
    type Recursive = int | Recursive  # ty: ignore[cyclic-type-alias-definition] -- exercise recursion protection.

    assert get_annotation_types(OptionalChoice) == {str, type(None)}
    assert get_annotation_types(Recursive) == {int, Any}


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


class TestPydanticGenericBindings:
    """Resolve model specializations and their inherited runtime bindings."""

    def test_specialization_and_named_subclass(self):
        class Model[ValueT](BaseModel):
            value: ValueT

        class Concrete(Model[int]):
            pass

        for cls in (Model[int], Concrete):
            assert resolve_generic_bindings(cls, Model).resolved_types == (int,)

    def test_partial_reordered_and_nested_models(self):
        class Item[ValueT](BaseModel):
            value: ValueT

        class Pair[LeftT, OtherT](BaseModel):
            pass

        class Reordered[FirstT, SecondT](Pair[SecondT, list[Item[FirstT]]]):
            pass

        partial = resolve_generic_bindings(Reordered, Pair)
        assert partial.unresolved == ("LeftT", "OtherT")

        class Concrete(Reordered[int, str]):
            pass

        for cls in (Reordered[int, str], Concrete):
            bindings = resolve_generic_bindings(cls, Pair)
            assert bindings.resolved_types == (str, list[Item[int]])
            assert bindings.is_resolved

    def test_unrelated_bases_and_mixed_python_generics(self):
        class Plain[ValueT]:
            pass

        class Model[ValueT](BaseModel, Plain[ValueT]):
            pass

        class Unrelated[ValueT](BaseModel):
            pass

        class Concrete(Unrelated[str], Model[int]):
            pass

        assert resolve_generic_bindings(Concrete, Model).resolved_types == (int,)
        assert resolve_generic_bindings(Concrete, Plain).resolved_types == (int,)

    def test_model_argument_in_an_ordinary_generic(self):
        class Item[ValueT](BaseModel):
            value: ValueT

        class Store[ValueT]:
            pass

        class BatchStore[ItemT](Store[list[Item[ItemT]]]):
            pass

        class Concrete(BatchStore[int]):
            pass

        assert resolve_generic_bindings(BatchStore, Store).unresolved == ("ValueT",)
        assert resolve_generic_bindings(Concrete, Store).resolved_types == (
            list[Item[int]],
        )

    def test_defaults_and_bare_subclasses(self):
        class Defaulted[ValueT = int](BaseModel):
            pass

        class Concrete(Defaulted):
            pass

        assert resolve_generic_bindings(Concrete, Defaulted).resolved_types == (int,)

        class Required[ValueT](BaseModel):
            pass

        class Bare(Required):
            pass

        assert resolve_generic_bindings(Bare, Required).unresolved == ("ValueT",)
        with pytest.raises(TypeError, match="must bind Required's type variables"):
            resolve_concrete_generic_bindings(
                Bare, Required, ValueT=GenericBindingRequirement("value_cls")
            )

    def test_diamond_paths(self):
        class Model[ValueT](BaseModel):
            pass

        class Left(Model[int]):
            pass

        class Right(Model[int]):
            pass

        class Other(Model[str]):
            pass

        class Consistent(Left, Right):
            pass

        class Conflicting(Left, Other):  # ty: ignore[invalid-generic-class]
            pass

        assert resolve_generic_bindings(Consistent, Model).resolved_types == (int,)
        with pytest.raises(TypeError, match="Conflicting .*Model bindings"):
            resolve_generic_bindings(Conflicting, Model)

    def test_pydantic_subclass_hook(self):
        class Model[ValueT: BaseModel](BaseModel):
            value_cls: ClassVar[type[BaseModel]]

            @classmethod
            def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
                super().__pydantic_init_subclass__(**kwargs)
                bindings = resolve_concrete_generic_bindings(
                    cls,
                    Model,
                    ValueT=GenericBindingRequirement("value_cls", BaseModel),
                )
                if bindings is not None:
                    cls.value_cls = bindings["ValueT"]

        class Item(BaseModel):
            pass

        class Other(BaseModel):
            pass

        class Intermediate[ValueT: BaseModel](Model[ValueT]):
            pass

        class Concrete(Intermediate[Item]):
            pass

        assert Concrete.value_cls is Item
        assert Intermediate[Other].value_cls is Other
        assert Model[Item].value_cls is Item
        assert "value_cls" not in Intermediate.__dict__
        assert "value_cls" not in Model.__dict__

        with pytest.raises(TypeError, match="must bind Model's type variables"):

            class Bare(Intermediate):
                pass

        with pytest.raises(TypeError, match="explicitly sets 'value_cls'"):

            class Explicit(Model[Item]):
                value_cls: ClassVar[type[BaseModel]] = Other

        with pytest.raises(TypeError, match="must bind ValueT to a BaseModel subclass"):
            Model[int]  # ty: ignore[invalid-type-arguments]


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
