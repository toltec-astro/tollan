"""Example consumers, deferred failures, and diagnostic context transport."""

import json
import pickle
import subprocess
import sys

import dask
import dask.array as da
import pytest
import xarray as xr

from docs.examples.pipeline_example import Scale, WriteSignal
from tollan.pipeline import SequentialPipeline, StepFailure, StepFailureKind


@pytest.fixture(autouse=True)
def netcdf_backend():
    # Use netCDF3 consistently for the example's small filesystem round trips.
    with xr.set_options(netcdf_engine_order=["scipy"]):
        yield


@pytest.fixture
def source():
    return xr.Dataset({"signal": ("sample", [1.0, 2.0])})


@pytest.mark.parametrize("has_context", [False, True])
def test_missing_result_records_failure_and_allows_later_step(
    source, tmp_path, has_context
):
    tree = xr.DataTree.from_dict({"raw": source})
    if has_context:
        Scale().create_context(tree)
    path = tmp_path / "scaled.nc"
    SequentialPipeline(steps=[WriteSignal(path=path), Scale()])(tree)

    context = WriteSignal.get_context(tree)
    assert not context.completed
    assert context.data is None
    assert [failure.kind for failure in context.failures] == [
        StepFailureKind.missing_input
    ]
    assert not path.exists()
    assert Scale.get_context(tree).completed


def test_writer_accepts_available_partial_result_and_overwrites(source, tmp_path):
    tree = xr.DataTree.from_dict({"raw": source})
    _, context = Scale()(tree, return_context=True)
    context.completed = False
    context.failures.append(StepFailure(message="An auxiliary result is unavailable."))
    path = tmp_path / "scaled.nc"
    path.write_text("old product")

    WriteSignal(path=path)(tree)

    assert WriteSignal.get_context(tree).completed
    assert not context.completed
    with xr.open_dataset(path, engine="scipy") as saved:
        assert saved.signal.values.tolist() == [2.0, 4.0]


def test_lazy_computation_failure_belongs_to_writer(tmp_path):
    @dask.delayed
    def unavailable_signal():
        msg = "Deferred signal read failed"
        raise RuntimeError(msg)

    source = xr.Dataset(
        {"signal": ("sample", da.from_delayed(unavailable_signal(), (2,), float))}
    )
    tree = xr.DataTree.from_dict({"raw": source})
    Scale()(tree)
    scale_context = Scale.get_context(tree)
    assert scale_context.completed
    assert scale_context.failures == []

    with (
        dask.config.set(scheduler="synchronous"),
        pytest.raises(RuntimeError, match="Deferred signal read failed"),
    ):
        WriteSignal(path=tmp_path / "scaled.nc")(tree)

    write_context = WriteSignal.get_context(tree)
    assert not write_context.completed
    assert write_context.data is None
    assert write_context.failures == [
        StepFailure(
            kind=StepFailureKind.exception,
            message="Deferred signal read failed",
            exception_type="RuntimeError",
        )
    ]
    assert Scale.get_context(tree) is scale_context
    assert scale_context.completed
    assert scale_context.failures == []


@pytest.mark.parametrize("alias", [None, "diagnostic"])
def test_context_supports_diagnostics_in_another_process(source, alias):
    tree = xr.DataTree.from_dict({"raw": source})
    Scale(alias=alias, factor=3)(tree)
    context = Scale.get_context(tree, alias=alias)
    diagnostic = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, pickle, sys; "
                "from docs.examples.pipeline_example import Scale; "
                "Scale.run = lambda *args, **kwargs: sys.exit('unexpected step run'); "
                "context = pickle.loads(sys.stdin.buffer.read()); "
                "print(json.dumps({'mean': context.data.signal.mean().item(), "
                "'factor': context.config.factor, 'alias': context.config.alias, "
                "'completed': context.completed, 'failures': len(context.failures)}))"
            ),
        ],
        input=pickle.dumps(context),
        capture_output=True,
        check=True,
    )
    assert json.loads(diagnostic.stdout) == {
        "mean": 4.5,
        "factor": 3.0,
        "alias": alias,
        "completed": True,
        "failures": 0,
    }
