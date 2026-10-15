"""Ordered column matching independent of result types and filename models."""

from enum import Enum
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from tollan.accessor.pandas.model_table import RecordRuleMapper


def test_generic_subclass_validates_rule_results_and_optional_default():
    class Kind(Enum):
        ready = "ready"

    class KindMapper(RecordRuleMapper[Kind]):
        default: None = None

    mapper = KindMapper.model_validate({"rules": [({"status": "ready"}, "ready")]})
    assert mapper.rules == (({"status": "ready"}, Kind.ready),)
    assert mapper({"status": "ready"}) is Kind.ready
    assert mapper({}) is None
    assert mapper.map_table(pd.DataFrame({"status": ["ready", "other"]})) == [
        Kind.ready,
        None,
    ]
    with pytest.raises(ValidationError, match="rules.0.1"):
        KindMapper(rules=(({}, None),))
    with pytest.raises(ValidationError, match="default"):
        KindMapper.model_validate({"rules": (), "default": Kind.ready})


@pytest.mark.parametrize("constraints", [{"status": []}, {3: "ready"}])
def test_rule_declarations_validate_constraints(constraints):
    with pytest.raises(ValidationError, match="rules.0.0"):
        RecordRuleMapper[int](rules=((constraints, 1),), default=None)


def test_generic_result_type_validates_default():
    with pytest.raises(ValidationError, match="default"):
        RecordRuleMapper[int](rules=(), default="invalid")


def test_rule_order_unconstrained_and_null_values():
    table = pd.DataFrame(
        {
            "format": pd.array(["a", "a", "b", None], dtype="string"),
            "suffix": pd.array([None, "", "", "x"], dtype="string"),
        },
        index=[2, 2, 1, 9],
    )
    before = table.copy()
    rules = [
        ({"ext": "a", "suffix": None}, "null suffix"),
        ({"ext": "a", "suffix": ...}, "other a"),
        ({"not_a_column": None}, "must not match"),
        ({"ext": None}, "null format"),
    ]
    assert RecordRuleMapper(rules=rules, default="unknown").map_table(
        table, column_names={"ext": "format"}
    ) == ["null suffix", "other a", "unknown", "null format"]
    pd.testing.assert_frame_equal(table, before)


def test_arbitrary_rule_results_are_preserved():
    class Kind(Enum):
        value_a = "a"

    outputs = [Kind.value_a, lambda: None, ("nested", [1]), {"value": 2}]
    result = RecordRuleMapper(
        rules=(({"number": i}, value) for i, value in enumerate(outputs[:-1])),
        default=outputs[-1],
    ).map_table(pd.DataFrame({"number": range(4)}))
    assert all(
        actual is expected for actual, expected in zip(result, outputs, strict=True)
    )


@pytest.mark.parametrize("size", [0, 3])
def test_empty_rules_and_catch_all(size):
    table = pd.DataFrame(index=range(size))
    assert RecordRuleMapper(rules=[], default=None).map_table(table) == [None] * size
    assert (
        RecordRuleMapper(rules=[({}, "all")], default=None).map_table(table)
        == ["all"] * size
    )


def test_shared_constraints_compared_once(monkeypatch):
    original = pd.Series.eq
    calls = []

    def compare(series, value, *args, **kwargs):
        calls.append((series.name, value))
        return original(series, value, *args, **kwargs)

    monkeypatch.setattr(pd.Series, "eq", compare)
    table = pd.DataFrame({"ext": ["nc", "nc", "ecsv"], "suffix": ["a", "b", "c"]})
    result = RecordRuleMapper(
        rules=[({"ext": "nc", "suffix": "a"}, 1), ({"ext": "nc", "suffix": "b"}, 2)],
        default=0,
    ).map_table(table)
    assert result == [1, 2, 0]
    assert calls.count(("ext", "nc")) == 1


@pytest.mark.parametrize("null", [None, float("nan"), pd.NA, pd.NaT])
def test_scalar_and_table_matching_agree(null):
    mapper = RecordRuleMapper(
        rules=[
            ({"missing": None}, "missing must not match"),
            ({"status": "ready", "extra": ...}, "ready"),
            ({"status": None}, "null"),
            ({"status": ""}, "empty"),
        ],
        default="unknown",
    )
    records = [{"status": item} for item in ("ready", null, "", "other")]
    expected = ["ready", "null", "empty", "unknown"]
    assert [mapper(record) for record in records] == expected
    assert [mapper(SimpleNamespace(**record)) for record in records] == expected
    table = pd.DataFrame(records, index=[2, 2, 9, 0])
    assert mapper.map_table(table) == expected
    assert [mapper(record) for record in table.itertuples(index=False)] == expected
    assert mapper({}) == "unknown"
    assert mapper(SimpleNamespace()) == "unknown"
    assert mapper({"status": "ready", "unused": 123}) == "ready"
    assert RecordRuleMapper(rules=[], default="empty")({}) == "empty"
    assert RecordRuleMapper(rules=[({}, "all")], default=None)({}) == "all"


def test_mapper_reuses_snapshotted_rules_and_preserves_enum_values():
    class Kind(Enum):
        ready = "ready"
        unknown = "unknown"

    constraints = {"status": "ready"}
    rules = [(constraints, Kind.ready)]
    mapper = RecordRuleMapper[Kind](rules=iter(rules), default=Kind.unknown)
    constraints["status"] = "changed"
    rules.clear()
    record = {"status": "ready"}
    assert mapper(record) is Kind.ready
    assert record == {"status": "ready"}
    for column in ("status", "file_status"):
        table = pd.DataFrame({column: ["ready", "other"]}, index=[5, 5])
        before = table.copy()
        values = mapper.map_table(table, column_names={"status": column})
        assert values == [Kind.ready, Kind.unknown]
        pd.testing.assert_frame_equal(table, before)
        table["kind"] = pd.array(values, dtype=object)
        assert table.kind.iloc[0] is Kind.ready
        assert table.kind.iloc[1] is Kind.unknown


def test_scalar_results_are_returned_without_invoking_or_copying():
    outputs = [lambda: pytest.fail("Result called"), ("nested", [1]), {"value": 2}]
    mapper = RecordRuleMapper(
        rules=[({"number": i}, value) for i, value in enumerate(outputs[:-1])],
        default=outputs[-1],
    )
    for i, value in enumerate(outputs):
        assert mapper({"number": i}) is value


@pytest.mark.parametrize("override", [None, pd.NA, 0, "", object()])
def test_call_default_override_preserves_matches_and_configured_default(override):
    configured = object()
    matched = object()
    mapper = RecordRuleMapper(
        rules=[({"number": 1}, matched), ({"number": 2}, None)], default=configured
    )
    records = [{"number": number} for number in (0, 1, 2)]
    table = pd.DataFrame(records, index=[7, 7, 1]).rename(columns={"number": "n"})
    before = table.copy()
    for result in (
        [mapper(record, default=override) for record in records],
        mapper.map_table(table, column_names={"number": "n"}, default=override),
    ):
        assert result[0] is override
        assert result[1] is matched
        assert result[2] is None
    assert mapper(records[0]) is configured
    assert mapper.map_table(table, column_names={"number": "n"})[0] is configured
    assert mapper.map_table(table.iloc[:0], default=override) == []
    pd.testing.assert_frame_equal(table, before)


def test_default_override_with_no_rules():
    mapper = RecordRuleMapper(rules=[], default="unknown")
    assert mapper({}, default=None) is None
    assert mapper.map_table(pd.DataFrame(index=[3, 3]), default=None) == [None, None]
    assert mapper({}) == "unknown"
