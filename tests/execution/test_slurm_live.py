"""Jobs run on a real Slurm cluster reached over SSH.

These tests run only when ``TOLLAN_SLURM_SHARED`` names the shared directory of
the Docker Slurm cluster in ``slurm_cluster/``: run ``just up`` and ``just test``
there.
"""

import os
import shutil
import time
import uuid
from pathlib import Path

import pytest

from tollan.config import RuntimeContext
from tollan.execution import (
    ExecutionPolicy,
    ExecutionRequest,
    JobRecord,
    JobState,
    SlurmProfile,
    SubmissionReceipt,
    SupervisionOutcomeKind,
    cancel_job,
    get_scheduler,
    supervise_job,
)

SHARED = os.environ.get("TOLLAN_SLURM_SHARED")
pytestmark = [
    pytest.mark.skipif(
        SHARED is None, reason="Set TOLLAN_SLURM_SHARED to run live Slurm tests."
    ),
]


@pytest.fixture(autouse=True)
def cluster_ssh(tmp_path, monkeypatch):
    """Route ``ssh`` from PATH through the cluster's SSH configuration."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "ssh"
    wrapper.write_text(f'#!/bin/sh\nexec /usr/bin/ssh -F {SHARED}/ssh/config "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


@pytest.fixture
def records_path():
    path = Path(str(SHARED)) / "jobs" / uuid.uuid4().hex[:8]
    yield path
    shutil.rmtree(path, ignore_errors=True)


def resolve(records_path, request, **profile):
    profile = {
        "kind": "slurm",
        "name": "cluster",
        "workloads": ".*",
        "job_records_path": str(records_path),
        "host": "tollan-slurm",
        "partition": "cpu",
        "account": "group",
        "qos": "normal",
        "env": {"GREETING": "hello"},
        "resources_default": {"cpus": 1, "memory": "100 MiB", "time_limit": "5 min"},
        "resources_max": {"cpus": 2, "memory": "500 MiB", "time_limit": "30 min"},
    } | profile
    rc = RuntimeContext()
    rc.update_default_config({"execution": {"profiles": [profile]}})
    return ExecutionPolicy(rc).resolve(
        ExecutionRequest.model_validate({"workload": "transform"} | request)
    )


def submit(records_path, command, request=None, **profile):
    spec = resolve(records_path, request or {}, **profile)
    record = JobRecord.create(spec, key="job-1", command=command)
    scheduler = get_scheduler(spec.profile)
    record.submit(scheduler)
    return record, scheduler


def output(record):
    return (record.path / JobRecord.output_filename).read_text().split()


def wait_for(record, scheduler, states, timeout=60):
    deadline = time.monotonic() + timeout
    while (status := record.status(scheduler)).state not in states:
        assert time.monotonic() < deadline, status
        time.sleep(0.5)
    return status


@pytest.mark.spec("placement-policy")
def test_a_job_runs_with_its_resources_and_environment(records_path):
    command = [
        "sh",
        "-c",
        (
            'echo "$(hostname)" "$SLURM_CPUS_PER_TASK" "$SLURM_MEM_PER_NODE" '
            '"$GREETING" "$OMP_NUM_THREADS" "$PWD"'
        ),
    ]
    request = {"resources": {"cpus": 2, "memory": "200 MiB", "threads": 2}}
    record, scheduler = submit(records_path, command, request)
    outcome = supervise_job(record, scheduler, poll_interval=0.5)
    assert outcome.kind == SupervisionOutcomeKind.succeeded, outcome.message
    assert outcome.status is not None
    assert (outcome.status.exit_code, outcome.status.native_state) == (0, "COMPLETED")
    host, cpus, memory, greeting, threads, directory = output(record)
    assert host in {"c1", "c2"}
    assert (cpus, memory, greeting, threads) == ("2", "200", "hello", "2")
    assert directory == str(record.path)
    assert record.read_exit_status() == 0


@pytest.mark.spec("job-records-and-schedulers")
def test_a_failing_job_reports_its_exit_status(records_path):
    record, scheduler = submit(records_path, ["sh", "-c", "exit 3"])
    outcome = supervise_job(record, scheduler, poll_interval=0.5)
    assert outcome.kind == SupervisionOutcomeKind.failed
    assert outcome.status is not None
    assert (outcome.status.exit_code, outcome.status.native_state) == (3, "FAILED")


@pytest.mark.spec("supervision")
def test_canceling_a_running_job_is_confirmed(records_path):
    record, scheduler = submit(records_path, ["sleep", "300"])
    wait_for(record, scheduler, {JobState.running})
    outcome = cancel_job(record, scheduler, timeout=60, poll_interval=0.5)
    assert outcome.kind == SupervisionOutcomeKind.canceled
    assert outcome.status is not None
    assert (outcome.status.state, outcome.status.native_state) == (
        JobState.canceled,
        "CANCELLED",
    )


@pytest.mark.spec("placement-policy")
@pytest.mark.parametrize(
    ("profile_nodes", "request_nodes", "host"),
    [({"excludes": ["c1"]}, None, "c2"), ({"excludes": []}, ["c1"], "c1")],
)
def test_node_selections_place_the_job(
    records_path, profile_nodes, request_nodes, host
):
    request = {} if request_nodes is None else {"nodes": request_nodes}
    record, scheduler = submit(records_path, ["hostname"], request, nodes=profile_nodes)
    outcome = supervise_job(record, scheduler, poll_interval=0.5)
    assert outcome.kind == SupervisionOutcomeKind.succeeded, outcome.message
    assert output(record) == [host]


@pytest.mark.spec("job-records-and-schedulers")
def test_reconciliation_finds_a_job_whose_receipt_was_lost(records_path):
    record, scheduler = submit(records_path, ["sleep", "300"])
    receipt = record.receipt
    assert receipt is not None
    # The submitter stopped after sbatch accepted the job, before the receipt.
    (record.path / JobRecord.receipt_filename).unlink()
    intent = record.path / JobRecord.intent_filename
    intent.write_text(intent.read_text().replace("host: ", "host: elsewhere-"))
    found = record.reconcile(scheduler)
    assert found is not None
    assert found.native_id == receipt.native_id
    cancel_job(record, scheduler, timeout=60, poll_interval=0.5)


@pytest.mark.spec("job-records-and-schedulers")
def test_an_unknown_job_id_is_unknown(records_path):
    record, scheduler = submit(records_path, ["true"])
    status = scheduler.get_status(record, SubmissionReceipt(native_id="999999"))
    assert status.state == JobState.unknown
    supervise_job(record, scheduler, poll_interval=0.5)


@pytest.mark.spec("orchestration-integration")
def test_a_dagster_asset_runs_a_job_on_the_cluster(records_path):
    dg = pytest.importorskip("dagster")
    from tollan.execution.dagster import PipesJobClient

    external = (
        "from dagster_pipes import open_dagster_pipes\n"
        "with open_dagster_pipes() as pipes:\n"
        "    pipes.report_asset_materialization(metadata={'rows': 3})\n"
    )
    spec = resolve(records_path, {})
    assert isinstance(spec.profile, SlurmProfile)

    @dg.asset
    def table(context: dg.AssetExecutionContext, client: PipesJobClient):
        invocation = client.run(
            context=context, spec=spec, key="job-1", command=["python3", "-c", external]
        )
        return invocation.get_materialize_result()

    client = PipesJobClient(poll_interval=0.5, final_message_timeout=30)
    result = dg.materialize([table], resources={"client": client})
    (materialization,) = result.asset_materializations_for_node("table")
    assert materialization.metadata["rows"].value == 3
