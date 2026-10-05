"""Tests for tollan.pipeline.step — Step/StepConfig/StepContext/SequentialPipeline."""

from __future__ import annotations

import json
import pickle

import pytest
import xarray as xr
from pydantic import BaseModel, ValidationError

from tollan.pipeline import (
    PIPELINE_CONTEXT_KEY,
    SequentialPipeline,
    Step,
    StepConfig,
    StepContext,
    StepContextDict,
    StepFailure,
    StepFailureKind,
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


class AddChild(AddStep):
    pass


class AddSibling(Step[AddConfig, AddContext]):
    pass


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


class FailingConfig(StepConfig):
    pass


class FailingContext(StepContext["FailingStep", FailingConfig]):
    pass


class FailingStep(Step[FailingConfig, FailingContext]):
    """A step that records an unsuccessful operation."""

    @classmethod
    def run(cls, data, context):
        context.failures.append(StepFailure(message="Operation failed."))


class CorrectContext(StepContext["CorrectStep", StepConfig]):
    data: float | None = None


class CorrectStep(Step[StepConfig, CorrectContext]):
    @classmethod
    def run(cls, data, context):
        for name in ("total", "correction"):
            if name not in data.attrs:
                context.failures.append(
                    StepFailure(
                        message=f"{name} is unavailable.",
                        kind=StepFailureKind.missing_input,
                        details={"input": name},
                    )
                )
        if context.failures:
            return
        context.data = data.attrs["total"] + data.attrs["correction"]


class SelectConfig(StepConfig):
    require_correction: bool = False


class SelectContext(StepContext["SelectStep", SelectConfig]):
    data: float | None = None


class SelectStep(Step[SelectConfig, SelectContext]):
    @classmethod
    def run(cls, data, context):
        corrected = None
        if CorrectStep.has_context(data):
            corrected = CorrectStep.get_context(data).data
        if corrected is None:
            if context.config.require_correction:
                context.failures.append(
                    StepFailure(
                        message="A corrected result is required.",
                        kind=StepFailureKind.missing_input,
                        details={"input": "corrected"},
                    )
                )
                return
            context.data = data.attrs["total"]
        else:
            context.data = corrected


class RaisingContext(StepContext["RaisingStep", StepConfig]):
    started: bool = False


class RaisingStep(Step[StepConfig, RaisingContext]):
    """Raises after changing data and its attached invocation record."""

    @classmethod
    def run(cls, data, context):
        assert cls.get_context(data) is context
        context.started = True
        context.failures.append(
            StepFailure(
                message="Reference is unavailable.",
                kind=StepFailureKind.missing_input,
                details={"input": "reference"},
            )
        )
        data.attrs["partial"] = True
        msg = "transition raised"
        raise ValueError(msg)


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
        ctx = AddContext(step_cls=AddStep, config=AddConfig(), completed=False)
        d[AddStep] = ctx
        assert d[AddStep] is ctx
        assert d[AddStep.context_key] is ctx

    def test_contains_via_class(self):
        d: StepContextDict = StepContextDict()
        assert AddStep not in d
        d[AddStep] = AddContext(step_cls=AddStep, config=AddConfig())
        assert AddStep in d


# ---------------------------------------------------------------------------
# get_pipeline_contexts
# ---------------------------------------------------------------------------


class TestGetPipelineContexts:
    @pytest.mark.parametrize("make_data", [make_dataset, make_datatree])
    def test_creates_once_and_reuses_attached_store(self, make_data):
        data = make_data()
        context = get_pipeline_contexts(data)
        assert isinstance(context, StepContextDict)
        assert data.attrs[PIPELINE_CONTEXT_KEY] is context
        assert get_pipeline_contexts(data) is context

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
        step = AddStep(alias="pass2")
        assert step.context_key != AddStep.context_key
        assert "AddStep" in step.context_key
        assert "pass2" in step.context_key

    def test_alias_does_not_change_original(self):
        key_before = AddStep.context_key
        AddStep(alias="x")
        assert AddStep.context_key == key_before

    def test_alias_does_not_overwrite_another_producers_primary_context(self):
        class Producer(AddStep):
            pass

        class Producer_second(AddStep):  # noqa: N801 -- reproduces a key collision
            pass

        source = make_dataset()
        first = Producer(alias="second", value=2)
        second = Producer_second(value=3)
        SequentialPipeline(steps=[first, second])(source)
        contexts = get_pipeline_contexts(source)
        assert len(contexts) == 2
        assert contexts[first].step_cls is Producer
        assert contexts[second].step_cls is Producer_second
        assert contexts[first].config.value == 2
        assert contexts[second].config.value == 3


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

    def test_indirect_generic_specialization(self):
        """Intermediate generic steps retain inference after specialization."""

        class LocalConfig(StepConfig):
            value: int = 1

        class LocalContext(StepContext["LocalStep", LocalConfig]):
            pass

        class GenericStep[ConfigT: StepConfig, ContextT: StepContext](
            Step[ConfigT, ContextT],
        ):
            pass

        class LocalStep(GenericStep[LocalConfig, LocalContext]):
            pass

        assert LocalStep.config_cls is LocalConfig
        assert LocalStep.context_cls is LocalContext

    def test_context_config_binding_must_match_step(self):
        """Duplicated static relationships are checked at class creation."""

        class ContextConfig(StepConfig):
            pass

        class StepConfigMismatch(StepConfig):
            pass

        class LocalContext(StepContext["InvalidStep", ContextConfig]):
            pass

        with pytest.raises(TypeError, match="config uses"):

            class InvalidStep(Step[StepConfigMismatch, LocalContext]):
                pass


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


class TestStepExecution:
    @pytest.mark.parametrize("make_data", [make_dataset, make_datatree])
    def test_run_stores_results_and_configuration(self, make_data):
        dt = make_data()
        step = AddStep(value=5.0)
        step(dt)
        assert AddStep.has_context(dt)
        ctx = AddStep.get_context(dt)
        assert isinstance(ctx, AddContext)
        assert ctx.completed is True
        assert ctx.data is not None
        assert ctx.data.result == pytest.approx(5.0)
        assert ctx.config is step.config

    def test_return_context_flag(self):
        dt = make_datatree()
        result_data, ctx = AddStep(value=2.0)(dt, return_context=True)
        assert result_data is dt
        assert isinstance(ctx, AddContext)
        assert ctx.data is not None
        assert ctx.data.result == pytest.approx(2.0)

    def test_direct_call_runs_even_when_disabled(self):
        dt = make_datatree()
        AddStep(value=11.0, enabled=False)(dt)
        assert dt.attrs["total"] == 11.0
        assert AddStep.get_context(dt).completed

    def test_failing_step_not_completed(self):
        dt = make_datatree()
        FailingStep()(dt)
        ctx = FailingStep.get_context(dt)
        assert ctx.completed is False
        assert ctx.failures == [StepFailure(message="Operation failed.")]

    def test_structured_failures_and_fresh_context_on_repeat(self):
        dt = make_datatree()
        step = CorrectStep()
        _, failed = step(dt, return_context=True)

        assert not failed.completed
        assert len(failed.failures) == 2
        assert all(
            failure.kind is StepFailureKind.missing_input for failure in failed.failures
        )
        assert failed.model_dump(mode="json")["failures"] == [
            {
                "message": "total is unavailable.",
                "kind": "missing_input",
                "exception_type": None,
                "details": {"input": "total"},
            },
            {
                "message": "correction is unavailable.",
                "kind": "missing_input",
                "exception_type": None,
                "details": {"input": "correction"},
            },
        ]
        restored = CorrectStep.load_context(CorrectStep.dump_context(failed))
        assert restored.failures == failed.failures

        dt.attrs["total"] = 10.0
        dt.attrs["correction"] = 2.0
        _, succeeded = step(dt, return_context=True)
        assert succeeded is not failed
        assert succeeded.completed
        assert succeeded.failures == []
        assert succeeded.failures is not failed.failures
        assert succeeded.data == 12.0
        assert CorrectStep.get_context(dt) is succeeded
        assert not failed.completed
        assert len(failed.failures) == 2

    @pytest.mark.parametrize("n_failures", [0, 2])
    def test_completion_is_set_after_run_from_recorded_failures(
        self, monkeypatch, n_failures
    ):
        def run(cls, data, context):
            assert cls.get_context(data) is context
            assert not context.completed
            context.failures.extend(
                StepFailure(message=f"Failure {i}") for i in range(n_failures)
            )
            assert not context.completed

        monkeypatch.setattr(FailingStep, "run", classmethod(run))
        dt = make_datatree()
        FailingStep()(dt)

        context = FailingStep.get_context(dt)
        assert context.completed is (n_failures == 0)
        assert len(context.failures) == n_failures

    @pytest.mark.parametrize("exception", [KeyboardInterrupt(), SystemExit(2)])
    def test_process_control_propagates_without_a_failure_record(
        self, monkeypatch, exception
    ):
        def interrupted(cls, data, context):
            raise exception

        monkeypatch.setattr(FailingStep, "run", classmethod(interrupted))
        dt = make_datatree()
        with pytest.raises(type(exception)) as caught:
            FailingStep()(dt)

        assert caught.value is exception
        context = FailingStep.get_context(dt)
        assert not context.completed
        assert context.failures == []

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


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------


class TestAlias:
    @pytest.mark.parametrize("step_cls", [AddStep, AddChild, AddSibling])
    @pytest.mark.parametrize("alias", [None, "repeat"])
    def test_shared_context_keeps_producer_and_pickles(self, step_cls, alias):
        step = step_cls(value=3, alias=alias)
        context = step.create_context(make_dataset())
        assert type(context) is AddContext
        assert step_cls.context_cls is AddContext
        assert context.step_cls is step_cls
        assert context.config_cls is AddConfig
        restored = pickle.loads(pickle.dumps(context))  # noqa: S301 -- test-owned context
        assert type(restored) is AddContext
        assert type(restored.make_step()) is step_cls
        assert restored.make_step().context_key == step.context_key
        assert restored.model_dump() == context.model_dump()
        restored_step = pickle.loads(pickle.dumps(step))  # noqa: S301 -- test-owned step
        assert type(restored_step) is step_cls
        assert restored_step.config == step.config

    @pytest.mark.parametrize("decoded", [False, True])
    def test_contexts_restore_with_their_producer_and_alias(self, decoded):
        data = make_dataset()
        steps = [
            AddStep(value=1),
            AddStep(alias="first", value=2),
            AddChild(alias="second", value=3),
        ]
        contexts = [step(data, return_context=True)[1] for step in steps]
        for step, context in zip(steps, contexts, strict=True):
            step_cls = type(step)
            assert type(context.make_step()) is step_cls
            assert context.make_step().config is context.config
            exported = step_cls.dump_context(context)
            assert "step_cls" not in json.loads(exported)
            if decoded:
                exported = json.loads(exported)
            restored = step_cls.load_context(exported)
            assert restored.step_cls is step_cls
            assert restored.model_dump() == context.model_dump()
            assert restored.make_step().context_key == step.context_key
            assert step_cls.get_context(data, alias=step.config.alias) is context
            assert get_pipeline_contexts(data)[step] is context
            restored.completed = False
            assert step_cls.get_context(data, alias=step.config.alias).completed
            context.completed = False
            assert not get_pipeline_contexts(data)[step].completed

    def test_alias_runs_independently_and_lookup_is_explicit(self):
        dt = make_datatree()
        primary = AddStep(value=1)
        first = AddStep(alias="first", value=10)
        second = AddStep(alias="second", value=100)
        SequentialPipeline(steps=[primary, first, second])(dt)
        assert type(first) is type(second) is AddStep
        assert AddStep.get_context(dt).config.value == 1
        assert AddStep.get_context(dt, alias="first").config.value == 10
        assert AddStep.get_context(dt, alias="second").config.value == 100
        assert AddStep.has_context(dt, alias="second")
        assert not AddStep.has_context(dt, alias="absent")
        assert second.get_context(dt) is AddStep.get_context(dt)
        contexts = get_pipeline_contexts(dt)
        assert contexts[second] is AddStep.get_context(dt, alias="second")
        assert first.context_key != second.context_key
        with pytest.raises(KeyError):
            AddStep.get_context(dt, alias="absent")


class TestContextRestoration:
    def test_json_context_in_netcdf_attribute(self, tmp_path):
        source = make_dataset()
        step = AddStep(value=3, alias="export")
        _, context = step(source, return_context=True)
        product = xr.Dataset(attrs={step.context_key: AddStep.dump_context(context)})
        path = tmp_path / "result.nc"
        product.to_netcdf(path, engine="scipy")
        with xr.open_dataset(path, engine="scipy") as reopened:
            value = reopened.attrs[step.context_key]
            assert isinstance(value, str)
            restored = AddStep.load_context(value)
            assert restored == context
            assert restored is not context
            assert restored.data is not None
            assert restored.data.result == 3
            assert restored.make_step().context_key == step.context_key
            assert reopened.attrs[step.context_key] is value
        assert AddStep.get_context(source, alias="export") is context

    def test_rejects_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            AddStep.load_context("{")

    @pytest.mark.parametrize("value", [None, [], 1, 1.5, True, "context"])
    def test_rejects_non_object_json(self, value):
        with pytest.raises(ValidationError) as caught:
            AddStep.load_context(json.dumps(value))
        assert caught.value.errors()[0]["type"] == "model_type"

    def test_rejects_invalid_exported_configuration(self):
        context = AddStep().create_context(make_dataset())
        exported = json.loads(AddStep.dump_context(context))
        exported["config"]["value"] = "not a number"
        with pytest.raises(ValidationError) as caught:
            AddStep.load_context(json.dumps(exported))
        assert caught.value.errors()[0]["loc"] == ("config", "value")


class TestStepFailure:
    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({}, "message"),
            ({"message": "failed", "kind": "unknown"}, "kind"),
            ({"message": "failed", "details": {"input": object()}}, "details"),
        ],
    )
    def test_rejects_invalid_failure_records(self, payload, field):
        with pytest.raises(ValidationError) as caught:
            StepFailure.model_validate(payload)
        assert caught.value.errors()[0]["loc"][0] == field


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

    def test_incomplete_operation_does_not_stop_later_operations(self):
        dt = make_datatree()
        dt.attrs["total"] = 10.0
        pipeline = SequentialPipeline(
            steps=[AddStep(value=3.0), FailingStep(), MultiplyStep(factor=5.0)]
        )

        assert pipeline(dt) is dt
        assert dt.attrs["total"] == 65.0
        assert AddStep.get_context(dt).completed
        assert not FailingStep.get_context(dt).completed
        assert MultiplyStep.get_context(dt).completed

    @pytest.mark.parametrize(
        ("correction", "enabled", "required", "selected"),
        [
            (5.0, True, False, 15.0),
            (None, True, False, 10.0),
            (5.0, False, False, 10.0),
            (None, True, True, None),
        ],
    )
    def test_consumer_selects_available_result_or_requires_it(
        self, correction, enabled, required, selected
    ):
        dt = make_datatree()
        dt.attrs["total"] = 10.0
        if correction is not None:
            dt.attrs["correction"] = correction
        pipeline = SequentialPipeline(
            steps=[
                CorrectStep(enabled=enabled),
                SelectStep(require_correction=required),
                AddStep(value=1.0),
            ]
        )

        assert pipeline(dt) is dt
        if enabled:
            assert CorrectStep.get_context(dt).completed == (correction is not None)
        else:
            assert not CorrectStep.has_context(dt)
        context = SelectStep.get_context(dt)
        assert context.data == selected
        assert context.completed == (selected is not None)
        if selected is None:
            assert len(context.failures) == 1
            assert context.failures[0].kind is StepFailureKind.missing_input
            assert context.failures[0].details == {"input": "corrected"}
        else:
            assert context.failures == []
        if enabled and correction is None:
            failures = CorrectStep.get_context(dt).failures
            assert len(failures) == 1
            assert failures[0].kind is StepFailureKind.missing_input
            assert failures[0].details == {"input": "correction"}
        assert AddStep.get_context(dt).completed
        assert dt.attrs["total"] == 11.0

    def test_exception_stops_with_live_incomplete_context_and_partial_data(self):
        dt = make_datatree()
        pipeline = SequentialPipeline(steps=[RaisingStep(), AddStep()])

        with pytest.raises(ValueError, match="transition raised") as caught:
            pipeline(dt)

        assert caught.traceback[-1].name == "run"
        context = RaisingStep.get_context(dt)
        assert context.started
        assert not context.completed
        assert context.failures == [
            StepFailure(
                message="Reference is unavailable.",
                kind=StepFailureKind.missing_input,
                details={"input": "reference"},
            ),
            StepFailure(
                message="transition raised",
                kind=StepFailureKind.exception,
                exception_type="ValueError",
            ),
        ]
        assert dt.attrs["partial"]
        assert not AddStep.has_context(dt)

    @pytest.mark.parametrize("already_run", [False, True])
    def test_skips_disabled_step_without_clearing_prior_context(self, already_run):
        dt = make_datatree()
        previous = None
        if already_run:
            _, previous = AddStep(value=100.0)(dt, return_context=True)
        dt.attrs["total"] = 1.0
        pipeline = SequentialPipeline(
            steps=[
                AddStep(value=100.0, enabled=False),
                MultiplyStep(factor=5.0),
            ],
        )
        pipeline(dt)  # type: ignore[call-arg]
        assert dt.attrs["total"] == pytest.approx(5.0)  # add was skipped
        assert AddStep.has_context(dt) is already_run
        if already_run:
            assert AddStep.get_context(dt) is previous
            assert previous is not None
            assert previous.completed
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
