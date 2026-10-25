"""Dagster assets run external processes as supervised jobs through Pipes."""

import sys
import time

import pytest

from tollan.config import RuntimeContext
from tollan.execution import (
    ExecutionPolicy,
    ExecutionRequest,
    JobRecord,
    JobState,
    LocalScheduler,
)

dg = pytest.importorskip("dagster")
from tollan.execution.dagster import PipesJobClient  # noqa: E402

EXTERNAL = """
import sys
from dagster_pipes import open_dagster_pipes

with open_dagster_pipes() as pipes:
    pipes.log.info("transforming")
    pipes.report_asset_materialization(metadata={"rows": int(sys.argv[1])})
"""


def make_spec(tmp_path, **profile):
    profile = {
        "name": "here",
        "workloads": ".*",
        "job_records_path": str(tmp_path / "jobs"),
    } | profile
    rc = RuntimeContext()
    rc.update_default_config({"execution": {"profiles": [profile]}})
    return ExecutionPolicy(rc).resolve(ExecutionRequest(workload="transform"))


def materialize(spec, command, *, key="job-1", contexts=None):
    @dg.asset
    def table(context: dg.AssetExecutionContext, client: PipesJobClient):
        if contexts is not None:
            contexts.append(context)
        invocation = client.run(context=context, spec=spec, key=key, command=command)
        return invocation.get_materialize_result()

    client = PipesJobClient(poll_interval=0.05, final_message_timeout=20)
    return dg.materialize([table], resources={"client": client}, raise_on_error=False)


def rows(result):
    (materialization,) = result.asset_materializations_for_node("table")
    return materialization.metadata["rows"].value


def external(rows=3):
    return [sys.executable, "-c", EXTERNAL, str(rows)]


def test_a_local_job_reports_its_materialization(tmp_path):
    spec = make_spec(tmp_path, kind="local")
    result = materialize(spec, external())
    assert result.success
    assert rows(result) == 3
    record = JobRecord.open(tmp_path / "jobs" / "job-1")
    assert record.history[-1].state == JobState.completed
    assert (record.path / "pipes_context.json").exists()
    assert (record.path / "pipes_messages.jsonl").exists()


def test_a_later_run_reattaches_and_reads_every_message(tmp_path):
    spec = make_spec(tmp_path, kind="local")
    first = materialize(spec, external())
    record = JobRecord.open(tmp_path / "jobs" / "job-1")
    receipt = record.receipt
    second = materialize(spec, external(rows=99))
    assert second.success
    assert rows(second) == rows(first) == 3
    assert JobRecord.open(record.path).receipt == receipt


def test_a_failing_job_fails_the_run(tmp_path):
    spec = make_spec(tmp_path, kind="local")
    result = materialize(spec, [sys.executable, "-c", "raise SystemExit(2)"])
    assert not result.success
    (failure,) = [event for event in result.all_events if event.is_step_failure]
    assert "exit status 2" in failure.step_failure_data.error.message


def test_a_slurm_job_reports_its_materialization(tmp_path, fake):
    spec = make_spec(
        tmp_path,
        kind="slurm",
        partition="cpu",
        resources_default={"cpus": 1, "memory": "1 GiB", "time_limit": "10 min"},
        resources_max={"cpus": 1, "memory": "1 GiB", "time_limit": "10 min"},
    )
    fake.reply("sbatch", stdout="1234\n", run=True)
    fake.reply("sacct", stdout="1234|COMPLETED|0:0\n")
    result = materialize(spec, external())
    assert result.success
    assert rows(result) == 3
    assert fake.commands() == ["sbatch", "sacct"]


def interrupt(monkeypatch, contexts, *, cancel_run):
    def supervise_job(*args, **kwargs):
        context = contexts[0]
        if cancel_run:
            run = context.instance.get_run_by_id(context.run.run_id)
            context.instance.report_run_canceling(run)
        raise dg.DagsterExecutionInterruptedError

    monkeypatch.setattr("tollan.execution.dagster.supervise_job", supervise_job)


def wait_for(record, state, timeout=20):
    scheduler = LocalScheduler()
    deadline = time.monotonic() + timeout
    while record.status(scheduler).state != state:
        assert time.monotonic() < deadline
        time.sleep(0.05)


def test_an_interrupted_run_leaves_its_job_running(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, kind="local")
    contexts = []
    interrupt(monkeypatch, contexts, cancel_run=False)
    command = [sys.executable, "-c", "import time; time.sleep(1)"]
    assert not materialize(spec, command, contexts=contexts).success
    record = JobRecord.open(tmp_path / "jobs" / "job-1")
    assert not record.cancel_requested
    wait_for(record, JobState.completed)


def test_a_canceled_run_cancels_its_job(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, kind="local")
    contexts = []
    interrupt(monkeypatch, contexts, cancel_run=True)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    assert not materialize(spec, command, contexts=contexts).success
    record = JobRecord.open(tmp_path / "jobs" / "job-1")
    assert record.cancel_requested
    wait_for(record, JobState.canceled)
