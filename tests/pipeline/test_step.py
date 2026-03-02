"""Tests for tollan.pipeline.step — Step/StepConfig/StepContext/SequentialPipeline."""

from __future__ import annotations

import pytest
import xarray as xr
from pydantic import BaseModel

from tollan.pipeline import (
    PIPELINE_CONTEXT_KEY,
    SequentialPipeline,
    Step,
    StepConfig,
    StepContext,
    StepContextDict,
    get_pipeline_contexts,
)

# ---------------------------------------------------------------------------
# Concrete fixtures
# ---------------------------------------------------------------------------


class AddConfig(StepConfig):
    value: float = 1.0


class AddData(BaseModel):
    result: float | None = None


class AddContext(StepContext["AddStep", AddConfig]):
    data: AddData | None = None


class AddStep(Step[AddConfig, AddContext]):
    """Adds config.value to data.attrs['total']."""

    @classmethod
    def run(cls, data, context):
        total = data.attrs.get("total", 0.0) + context.config.value
        data.attrs["total"] = total
        context.data = AddData(result=total)
        return True


class MultiplyConfig(StepConfig):
    factor: float = 2.0


class MultiplyData(BaseModel):
    result: float | None = None


class MultiplyContext(StepContext["MultiplyStep", MultiplyConfig]):
    data: MultiplyData | None = None


class MultiplyStep(Step[MultiplyConfig, MultiplyContext]):
    """Multiplies data.attrs['total'] by config.factor."""

    @classmethod
    def run(cls, data, context):
        total = data.attrs.get("total", 1.0) * context.config.factor
        data.attrs["total"] = total
        context.data = MultiplyData(result=total)
        return True


class FailingConfig(StepConfig):
    pass


class FailingContext(StepContext["FailingStep", FailingConfig]):
    pass


class FailingStep(Step[FailingConfig, FailingContext]):
    """A step whose run() returns False (incomplete)."""

    @classmethod
    def run(cls, data, context):
        return False  # signal incomplete


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_dataset() -> xr.Dataset:
    return xr.Dataset()


def make_datatree() -> xr.DataTree:
    return xr.DataTree()


# ---------------------------------------------------------------------------
# StepContextDict
# ---------------------------------------------------------------------------


class TestStepContextDict:
    def test_resolve_str(self):
        assert StepContextDict.resolve_key("SomeKey") == "SomeKey"

    def test_resolve_step_class(self):
        key = StepContextDict.resolve_key(AddStep)
        assert "AddStep" in key

    def test_resolve_step_instance(self):
        step = AddStep()
        key = StepContextDict.resolve_key(step)
        assert "AddStep" in key

    def test_resolve_callable(self):
        def my_func():
            pass

        key = StepContextDict.resolve_key(my_func)
        assert "my_func" in key

    def test_resolve_invalid(self):
        with pytest.raises(TypeError):
            StepContextDict.resolve_key(42)

    def test_setitem_getitem_via_class(self):
        d: StepContextDict = StepContextDict()
        ctx = AddContext(config=AddConfig(), completed=False)
        d[AddStep] = ctx
        assert d[AddStep] is ctx
        assert d[AddStep.context_key] is ctx

    def test_contains_via_class(self):
        d: StepContextDict = StepContextDict()
        assert AddStep not in d
        d[AddStep] = AddContext(config=AddConfig())
        assert AddStep in d


# ---------------------------------------------------------------------------
# get_pipeline_contexts
# ---------------------------------------------------------------------------


class TestGetPipelineContexts:
    def test_creates_on_first_access_dataset(self):
        ds = make_dataset()
        pctx = get_pipeline_contexts(ds)
        assert isinstance(pctx, StepContextDict)
        assert PIPELINE_CONTEXT_KEY in ds.attrs

    def test_creates_on_first_access_datatree(self):
        dt = make_datatree()
        pctx = get_pipeline_contexts(dt)
        assert isinstance(pctx, StepContextDict)
        assert PIPELINE_CONTEXT_KEY in dt.attrs

    def test_same_object_on_repeated_access(self):
        dt = make_datatree()
        pctx1 = get_pipeline_contexts(dt)
        pctx2 = get_pipeline_contexts(dt)
        assert pctx1 is pctx2

    def test_meta_fallback(self):
        class LegacyData:
            def __init__(self):
                self.meta = {}

        obj = LegacyData()
        pctx = get_pipeline_contexts(obj)
        assert isinstance(pctx, StepContextDict)
        assert PIPELINE_CONTEXT_KEY in obj.meta

    def test_raises_for_plain_object(self):
        with pytest.raises(TypeError, match="no .attrs or .meta"):
            get_pipeline_contexts(object())


# ---------------------------------------------------------------------------
# Step.context_key
# ---------------------------------------------------------------------------


class TestContextKey:
    def test_class_access(self):
        key = AddStep.context_key
        assert isinstance(key, str)
        assert "AddStep" in key

    def test_instance_access(self):
        step = AddStep()
        assert step.context_key == AddStep.context_key

    def test_different_steps_have_different_keys(self):
        assert AddStep.context_key != MultiplyStep.context_key

    def test_alias(self):
        AliasedAdd = AddStep.alias("pass2")
        assert AliasedAdd.context_key != AddStep.context_key
        assert "AddStep" in AliasedAdd.context_key
        assert "pass2" in AliasedAdd.context_key

    def test_alias_does_not_change_original(self):
        key_before = AddStep.context_key
        AddStep.alias("x")
        assert AddStep.context_key == key_before


# ---------------------------------------------------------------------------
# Step construction
# ---------------------------------------------------------------------------


class TestStepConstruction:
    def test_default_config_from_kwargs(self):
        step = AddStep(value=3.0)
        assert step.config.value == 3.0

    def test_default_config_no_args(self):
        step = AddStep()
        assert step.config.value == 1.0  # default

    def test_config_object(self):
        cfg = AddConfig(value=7.0)
        step = AddStep(cfg)
        assert step.config.value == 7.0

    def test_config_object_with_kwargs_override(self):
        cfg = AddConfig(value=7.0)
        step = AddStep(cfg, value=9.0)
        assert step.config.value == 9.0

    def test_wrong_type_raises(self):
        with pytest.raises(ValueError, match="not a AddConfig"):
            AddStep("bad")

    def test_too_many_args_raises(self):
        with pytest.raises(ValueError, match="too many"):
            AddStep(AddConfig(), AddConfig())


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


class TestStepExecution:
    def test_run_stores_context(self):
        dt = make_datatree()
        step = AddStep(value=5.0)
        step(dt)
        assert AddStep.has_context(dt)
        ctx = AddStep.get_context(dt)
        assert isinstance(ctx, AddContext)
        assert ctx.completed is True
        assert ctx.data is not None
        assert ctx.data.result == pytest.approx(5.0)

    def test_run_uses_dataset(self):
        ds = make_dataset()
        AddStep(value=3.0)(ds)
        ctx = AddStep.get_context(ds)
        assert ctx.data is not None
        assert ctx.data.result == pytest.approx(3.0)

    def test_return_context_flag(self):
        dt = make_datatree()
        result_data, ctx = AddStep(value=2.0)(dt, return_context=True)
        assert result_data is dt
        assert isinstance(ctx, AddContext)
        assert ctx.data is not None
        assert ctx.data.result == pytest.approx(2.0)

    def test_context_config_is_stored(self):
        dt = make_datatree()
        step = AddStep(value=11.0)
        step(dt)
        ctx = AddStep.get_context(dt)
        assert ctx.config.value == pytest.approx(11.0)

    def test_failing_step_not_completed(self):
        dt = make_datatree()
        FailingStep()(dt)
        ctx = FailingStep.get_context(dt)
        assert ctx.completed is False

    def test_second_call_replaces_context(self):
        dt = make_datatree()
        AddStep(value=1.0)(dt)
        AddStep(value=99.0)(dt)  # overwrites
        ctx = AddStep.get_context(dt)
        assert ctx.config.value == pytest.approx(99.0)

    def test_get_context_raises_if_not_run(self):
        dt = make_datatree()
        with pytest.raises(KeyError):
            AddStep.get_context(dt)

    def test_has_context_false_before_run(self):
        dt = make_datatree()
        assert not AddStep.has_context(dt)

    def test_has_context_true_after_run(self):
        dt = make_datatree()
        AddStep()(dt)
        assert AddStep.has_context(dt)


# ---------------------------------------------------------------------------
# Cross-step context access
# ---------------------------------------------------------------------------


class TestCrossStepContextAccess:
    def test_two_steps_independent_contexts(self):
        dt = make_datatree()
        AddStep(value=10.0)(dt)
        MultiplyStep(factor=3.0)(dt)
        ctx_add = AddStep.get_context(dt)
        ctx_mul = MultiplyStep.get_context(dt)
        assert ctx_add.data is not None
        assert ctx_mul.data is not None
        assert ctx_add.data.result == pytest.approx(10.0)
        assert ctx_mul.data.result == pytest.approx(30.0)

    def test_cross_step_typed_access(self):
        """KidsFind-like step reading SweepCheck-like step's context."""
        dt = make_datatree()
        AddStep(value=5.0)(dt)
        # MultiplyStep reads AddStep's result
        add_ctx = AddStep.get_context(dt)
        assert add_ctx.data is not None
        dt.attrs["total"] = add_ctx.data.result
        MultiplyStep(factor=2.0)(dt)
        ctx_mul = MultiplyStep.get_context(dt)
        assert ctx_mul.data is not None
        assert ctx_mul.data.result == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------


class TestAlias:
    def test_alias_runs_independently(self):
        dt = make_datatree()
        AddPass1 = AddStep.alias("pass1")
        AddPass2 = AddStep.alias("pass2")
        AddPass1(value=1.0)(dt)
        AddPass2(value=100.0)(dt)
        ctx1 = AddPass1.get_context(dt)
        ctx2 = AddPass2.get_context(dt)
        assert ctx1.config.value == pytest.approx(1.0)
        assert ctx2.config.value == pytest.approx(100.0)
        assert AddPass1.context_key != AddPass2.context_key


# ---------------------------------------------------------------------------
# SequentialPipeline
# ---------------------------------------------------------------------------


class TestSequentialPipeline:
    def test_runs_steps_in_order(self):
        dt = make_datatree()
        dt.attrs["total"] = 10.0
        pipeline = SequentialPipeline(
            steps=[MultiplyStep(factor=2.0), AddStep(value=3.0)],
        )
        result = pipeline(dt)  # type: ignore[call-arg]
        assert result is dt
        assert dt.attrs["total"] == pytest.approx(23.0)

    def test_skips_disabled_step(self):
        dt = make_datatree()
        dt.attrs["total"] = 1.0
        pipeline = SequentialPipeline(
            steps=[
                AddStep(value=100.0, enabled=False),
                MultiplyStep(factor=5.0),
            ],
        )
        pipeline(dt)  # type: ignore[call-arg]
        assert dt.attrs["total"] == pytest.approx(5.0)  # add was skipped
        assert not AddStep.has_context(dt)
        assert MultiplyStep.has_context(dt)

    def test_empty_pipeline(self):
        dt = make_datatree()
        pipeline = SequentialPipeline(steps=[])
        result = pipeline(dt)  # type: ignore[call-arg]
        assert result is dt

    def test_contexts_accessible_after_pipeline(self):
        dt = make_datatree()
        pipeline = SequentialPipeline(
            steps=[AddStep(value=7.0), MultiplyStep(factor=3.0)],
        )
        pipeline(dt)  # type: ignore[call-arg]
        add_ctx = AddStep.get_context(dt)
        mul_ctx = MultiplyStep.get_context(dt)
        assert add_ctx.data is not None
        assert mul_ctx.data is not None
        assert add_ctx.data.result == pytest.approx(7.0)
        assert mul_ctx.data.result == pytest.approx(21.0)
