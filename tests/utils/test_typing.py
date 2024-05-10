from typing import Annotated

import astropy.units as u

from tollan.utils.typing import get_physical_type_from_quantity_type, get_typing_args


def test_get_typing_args():
    T1 = Annotated[list, list[int], type[dict[str, dict]]]  # noqa: N806

    class D(dict[str, dict]): ...

    T2 = Annotated[list, list[int], D]  # noqa: N806

    class E(D): ...

    class F(E): ...

    assert get_typing_args(T1) == [list, list[int], type[dict[str, dict]]]
    assert get_typing_args(T1, max_depth=None) == [list, int, str, dict]
    assert get_typing_args(T2, max_depth=None) == [list, int, str, dict]
    assert get_typing_args(D, max_depth=None) == [str, dict]
    assert get_typing_args(int, max_depth=None) == []
    assert get_typing_args(E, max_depth=1) == [dict[str, dict]]
    assert get_typing_args(F, max_depth=1) == [dict[str, dict]]


# def test_get_typing_args_generic():
#
#     class T0: ...
#
#     class T1(T0): ...
#
#     class G0: ...
#
#     T = TypeVar("T")
#     U = TypeVar("U", bound=T0)
#
#     class G1(G0, Generic[T, U]): ...
#
#     class G2(G1[T0, T1]): ...
#
#     assert get_typing_args(G2) == [T0, T1]
#

Q1 = u.Quantity[u.m]
Q2 = u.Quantity["time"]


def test_quantity_physical_type():
    assert get_physical_type_from_quantity_type(Q1) == "length"
    assert get_physical_type_from_quantity_type(Q2) == "time"
