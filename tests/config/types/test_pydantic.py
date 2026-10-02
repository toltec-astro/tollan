"""Declared defaults are inspected without constructing a configuration model."""

from typing import ClassVar

import pytest
from pydantic import Field
from pydantic_core import PydanticUndefined

from tollan.config import FrozenBaseModel
from tollan.config.types import FieldDefaults


def test_field_defaults_preserves_required_and_factory_semantics():
    calls = []

    def make_value():
        calls.append(True)
        return 42

    class Config(FrozenBaseModel):
        defaults: ClassVar[FieldDefaults] = FieldDefaults()
        declared: int = 3
        required: int
        computed: int = Field(default_factory=make_value)

    assert Config.defaults["declared"] == 3
    assert Config.defaults["required"] is PydanticUndefined
    assert Config.defaults["computed"] is PydanticUndefined
    assert calls == []
    with pytest.raises(KeyError, match="unknown"):
        Config.defaults["unknown"]
