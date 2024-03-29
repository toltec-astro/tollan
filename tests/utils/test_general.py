from typing import ClassVar

import pytest

from tollan.utils.general import getname, getobj


class SomeClass:
    some_clsattr: ClassVar[str] = ...

    @classmethod
    def some_clsmethod(): ...

    some_attr: str = ...

    def some_method(): ...

    @property
    def some_property(self): ...


def some_func(): ...


def test_getname():
    assert getname(SomeClass) == "tests.utils.test_general:SomeClass"
    with pytest.raises(TypeError):
        getname(SomeClass.some_clsattr)
    assert (
        getname(SomeClass.some_clsmethod)
        == "tests.utils.test_general:SomeClass.some_clsmethod"
    )
    with pytest.raises(TypeError):
        getname(SomeClass.some_property)
    assert (
        getname(SomeClass().some_method)
        == "tests.utils.test_general:SomeClass.some_method"
    )
    with pytest.raises(TypeError):
        getname(SomeClass().some_attr)
    with pytest.raises(TypeError):
        getname(SomeClass().some_property)
    assert getname(some_func) == "tests.utils.test_general:some_func"


def test_getobj():
    assert getobj("tollan.utils.general:getname") is getname


def test_roundtrip():
    assert getobj(getname(getobj)) is getobj
