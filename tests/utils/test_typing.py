from typing import Annotated

import astropy.units as u

from tollan.utils.typing import get_physical_type_from_quantity_type, get_typing_args

T1 = Annotated[list, list[int], type[dict[str, dict]]]


class D(dict[str, dict]):
    pass


T2 = Annotated[list, list[int], D]


class E(D): ...


class F(E): ...


def test_get_typing_args():
    assert get_typing_args(T1) == [list, list[int], type[dict[str, dict]]]
    assert get_typing_args(T1, max_depth=None) == [list, int, str, dict]
    assert get_typing_args(T2, max_depth=None) == [list, int, str, dict]
    assert get_typing_args(D, max_depth=None) == [str, dict]
    assert get_typing_args(int, max_depth=None) == []
    assert get_typing_args(E, max_depth=1) == [dict[str, dict]]
    assert get_typing_args(F, max_depth=1) == [dict[str, dict]]


Q1 = u.Quantity[u.m]
Q2 = u.Quantity["time"]


def test_quantity_physical_type():
    assert get_physical_type_from_quantity_type(Q1) == "length"
    assert get_physical_type_from_quantity_type(Q2) == "time"
