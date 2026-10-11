"""Coarse local regression benchmarks; fixture construction is not timed."""

import pandas as pd
import pytest
from pydantic import BaseModel

from tollan.accessor.pandas.model_table import (
    ModelColumnMapper,
    ModelTableAccessor,
    RecordRuleMapper,
    ScalarColumnRule,
)


class Sample(BaseModel):
    """Representative scalar columns for repeated projection."""

    label: str
    count: int
    value: float
    valid: bool


def make_column_mapper():
    """Prepare the naming and scalar conversion rules."""
    return ModelColumnMapper(
        name_rules=[(r".+", r"\g<0>")], type_rules=[ScalarColumnRule()]
    )


@pytest.mark.parametrize("size", [1_000, 100_000])
def test_record_rules_table(benchmark, size):
    """Track vectorized matching with shared constraints and unmatched rows."""
    table = pd.DataFrame(
        {"format": ["nc"] * size, "kind": [i % 20 for i in range(size)]}
    )
    mapper = RecordRuleMapper(
        [({"format": "nc", "kind": i}, i) for i in range(16)], default=-1
    )
    result = benchmark(mapper.map_table, table)
    assert result == [i % 20 if i % 20 < 16 else -1 for i in range(size)]


def test_column_mapper_preparation(benchmark):
    """Track preparation separately from repeated use."""
    mapper = benchmark(make_column_mapper)
    assert list(mapper(Sample)) == ["label", "count", "value", "valid"]


def test_column_mapper_reuse(benchmark):
    """Track resolving columns with an already prepared mapper."""
    mapper = make_column_mapper()
    columns = benchmark(mapper, Sample)
    assert list(columns) == ["label", "count", "value", "valid"]


@pytest.mark.parametrize("size", [100, 10_000])
def test_model_table_projection(benchmark, size):
    """Track projection without charging model validation to table creation."""
    models = [
        Sample(label="sample", count=i, value=1.5, valid=True) for i in range(size)
    ]
    columns = make_column_mapper()(Sample)
    table = benchmark(ModelTableAccessor.from_models, models, columns=columns)
    assert table.shape == (size, 4)
    assert table["count"].tolist() == list(range(size))
    assert table["value"].eq(1.5).all()
