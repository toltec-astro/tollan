"""Slurm jobs run through scheduler commands on a submission host."""

from datetime import UTC, datetime

import pytest

from tollan.config import RuntimeContext
from tollan.execution import (
    ExecutionPolicy,
    ExecutionRequest,
    JobRecord,
    JobState,
    LocalScheduler,
    LocalTransport,
    SchedulerCommandError,
    SlurmScheduler,
    SshTransport,
    TransportError,
    get_scheduler,
)

PROFILE = {
    "kind": "slurm",
    "name": "cluster",
    "workloads": ".*",
    "partition": "cpu",
    "account": "group",
    "qos": "normal",
    "nodes": {"excludes": ["cpu3"]},
    "resources_default": {"cpus": 4, "memory": "8 GiB", "time_limit": "90 min"},
    "resources_max": {"cpus": 16, "memory": "64 GiB", "time_limit": "2 d"},
}


def make_spec(tmp_path, *, request_nodes=None, **changes):
    profile = PROFILE | {"job_records_path": str(tmp_path / "jobs")} | changes
    rc = RuntimeContext()
    rc.update_default_config({"execution": {"profiles": [profile]}})
    request = {"workload": "transform"}
    if request_nodes is not None:
        request["nodes"] = request_nodes
    return ExecutionPolicy(rc).resolve(ExecutionRequest.model_validate(request))


def make_record(tmp_path, **changes):
    spec = make_spec(tmp_path, **changes)
    return JobRecord.create(spec, key="job-1", command=["true"])


SCHEDULER = SlurmScheduler(LocalTransport())


# Submission


def test_submission_runs_sbatch_with_the_job_spec(tmp_path, fake):
    fake.reply("sinfo", stdout="cpu1\ncpu2\ncpu3\ncpu2\n")
    fake.reply("sbatch", stdout="1234\n")
    record = make_record(tmp_path)
    receipt = record.submit(SCHEDULER)
    assert (receipt.native_id, receipt.cluster) == ("1234", None)
    assert fake.calls == [
        ["sinfo", "-h", "-N", "--partition=cpu", "--format=%N"],
        [
            "sbatch",
            "--parsable",
            "--no-requeue",
            "--job-name=job-1",
            f"--chdir={record.path}",
            f"--output={record.path / 'output.log'}",
            "--nodes=1",
            "--ntasks=1",
            "--partition=cpu",
            "--account=group",
            "--qos=normal",
            "--cpus-per-task=4",
            "--mem=8192M",
            "--time=90",
            "--exclude=cpu3",
            str(record.path / "job.sh"),
        ],
    ]


def test_submission_without_node_restrictions_skips_the_node_query(tmp_path, fake):
    fake.reply("sbatch", stdout="1234;hpc\n")
    record = make_record(tmp_path, nodes={"excludes": []}, account=None, qos=None)
    receipt = record.submit(SCHEDULER)
    assert (receipt.native_id, receipt.cluster) == ("1234", "hpc")
    (sbatch,) = fake.calls
    assert not [
        arg for arg in sbatch if arg.startswith(("--exclude", "--acc", "--qos"))
    ]


def test_requested_nodes_narrow_the_excluded_complement(tmp_path, fake):
    fake.reply("sinfo", stdout="cpu1\ncpu2\ncpu3\n")
    fake.reply("sbatch", stdout="1234\n")
    record = JobRecord.create(
        make_spec(tmp_path, request_nodes={"pattern": "cpu[23]"}),
        key="job-1",
        command=["true"],
    )
    record.submit(SCHEDULER)
    assert "--exclude=cpu1,cpu3" in fake.calls[-1]


def test_an_empty_node_selection_is_not_submitted(tmp_path, fake):
    fake.reply("sinfo", stdout="cpu1\ncpu2\ncpu3\n")
    record = JobRecord.create(
        make_spec(tmp_path, request_nodes=["cpu3"]), key="job-1", command=["true"]
    )
    with pytest.raises(ValueError, match="No node of partition 'cpu'"):
        record.submit(SCHEDULER)
    assert "sbatch" not in fake.commands()
    assert record.is_unresolved


def test_a_rejected_submission_leaves_the_record_unresolved(tmp_path, fake):
    fake.reply("sinfo", stdout="cpu1\n")
    fake.reply("sbatch", exit=1, stderr="sbatch: error: invalid partition\n")
    record = make_record(tmp_path)
    with pytest.raises(SchedulerCommandError, match="invalid partition") as error:
        record.submit(SCHEDULER)
    assert error.value.returncode == 1
    assert record.is_unresolved


# Status and cancellation


@pytest.mark.parametrize(
    ("native", "exit_code", "expected"),
    [
        ("PENDING", "0:0", (JobState.queued, None)),
        ("RUNNING", "0:0", (JobState.running, None)),
        ("COMPLETED", "0:0", (JobState.completed, 0)),
        ("FAILED", "2:0", (JobState.failed, 2)),
        ("OUT_OF_MEMORY", "0:125", (JobState.failed, 0)),
        ("TIMEOUT", "0:15", (JobState.failed, 0)),
        ("CANCELLED by 1000", "0:15", (JobState.canceled, 0)),
        ("SPECIAL_EXIT", "0:0", (JobState.unknown, None)),
    ],
)
def test_accounting_states_map_to_job_states(
    tmp_path, fake, native, exit_code, expected
):
    fake.reply("sbatch", stdout="1234\n")
    record = make_record(tmp_path, nodes={"excludes": []})
    record.submit(SCHEDULER)
    fake.reply("sacct", stdout=f"1233|COMPLETED|0:0\n1234|{native}|{exit_code}\n")
    status = record.status(SCHEDULER)
    assert (status.state, status.exit_code) == expected
    assert status.native_state == native.split()[0]


def test_queued_jobs_missing_from_accounting_are_read_from_the_queue(tmp_path, fake):
    fake.reply("sbatch", stdout="1234\n")
    record = make_record(tmp_path, nodes={"excludes": []})
    record.submit(SCHEDULER)
    fake.reply("squeue", stdout="1234|PENDING\n")
    assert record.status(SCHEDULER).state == JobState.queued
    fake.reply("squeue", stdout="")
    status = record.status(SCHEDULER)
    assert (status.state, status.native_state) == (JobState.unknown, None)


def test_cluster_qualified_jobs_are_queried_and_canceled_on_their_cluster(
    tmp_path, fake
):
    fake.reply("sbatch", stdout="1234;hpc\n")
    fake.reply("sacct", stdout="1234|RUNNING|0:0\n")
    record = make_record(tmp_path, nodes={"excludes": []})
    record.submit(SCHEDULER)
    record.status(SCHEDULER)
    record.cancel(SCHEDULER)
    sacct, scancel = fake.calls[-2:]
    assert "--clusters=hpc" in sacct
    assert scancel == ["scancel", "--clusters=hpc", "1234"]


# Reconciliation


def test_reconciliation_matches_the_key_and_record_directory(tmp_path, fake):
    record = make_record(tmp_path, nodes={"excludes": []})
    since = datetime(2026, 1, 2, 12, tzinfo=UTC)
    intent = record.path / JobRecord.intent_filename
    intent.write_text(f"host: elsewhere\npid: 1\ntime: {since.isoformat()}\n")
    fake.reply("squeue", stdout="1235|/elsewhere\n")
    fake.reply("sacct", stdout=f"1234|{record.path}\n1236|/other\n")
    receipt = record.reconcile(SCHEDULER)
    assert receipt is not None
    assert receipt.native_id == "1234"
    (sacct,) = [call for call in fake.calls if call[0] == "sacct"]
    assert "--name=job-1" in sacct
    assert "--starttime=2026-01-01T12:00:00" in sacct


# Transports


def test_missing_scheduler_commands_are_transport_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(TransportError, match="Could not run sinfo"):
        LocalTransport().run(["sinfo"])


def test_ssh_runs_quoted_commands_on_the_host(fake):
    transport = SshTransport("login", options=["-p", "2222"])
    assert transport.run(["printf", "%s|", "a b", "c"]) == "a b|c|"
    assert fake.calls[0][:7] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-p",
        "2222",
    ]
    assert fake.calls[0][7:] == ["login", "printf '%s|' 'a b' c"]


def test_ssh_distinguishes_connection_failures_from_command_failures(fake):
    transport = SshTransport("login")
    with pytest.raises(SchedulerCommandError) as error:
        transport.run(["sh", "-c", "exit 3"])
    assert error.value.returncode == 3
    fake.reply("ssh", exit=255, stderr="ssh: connect to host login: refused\n")
    with pytest.raises(TransportError, match="refused"):
        transport.run(["sacct"])


def test_commands_that_do_not_finish_in_time_are_transport_failures(fake):
    fake.reply("ssh", sleep=5)
    with pytest.raises(TransportError, match="timed out"):
        SshTransport("login", timeout=0.5).run(["sacct"])


def test_profiles_select_their_scheduler_and_transport(tmp_path):
    local = {"kind": "local", "name": "laptop", "workloads": ".*"}
    rc = RuntimeContext()
    rc.update_default_config(
        {
            "execution": {
                "profiles": [
                    local | {"job_records_path": str(tmp_path)},
                    PROFILE | {"name": "here", "job_records_path": str(tmp_path)},
                    PROFILE
                    | {"name": "there", "host": "login", "job_records_path": "/j"},
                ]
            }
        }
    )
    laptop, here, there = ExecutionPolicy(rc).config.profiles
    assert isinstance(get_scheduler(laptop), LocalScheduler)
    for profile, transport in ((here, LocalTransport), (there, SshTransport)):
        scheduler = get_scheduler(profile)
        assert isinstance(scheduler, SlurmScheduler)
        assert isinstance(scheduler.transport, transport)
    scheduler = get_scheduler(there)
    assert isinstance(scheduler, SlurmScheduler)
    assert isinstance(scheduler.transport, SshTransport)
    assert scheduler.transport.host == "login"
