"""Job records keep durable, once-only state of one external job."""

import subprocess
import sys
import threading
from datetime import UTC, datetime

import pytest

from tollan.config import RuntimeContext
from tollan.execution import (
    ExecutionPolicy,
    ExecutionRequest,
    JobRecord,
    JobState,
    JobStatus,
    SubmissionReceipt,
    SubmissionUnresolvedError,
)

from .schedulers import RecordingScheduler

COMMAND = [sys.executable, "-c", "print('done')"]


def make_spec(tmp_path, env):
    rc = RuntimeContext()
    rc.update_default_config(
        {
            "execution": {
                "profiles": [
                    {
                        "kind": "local",
                        "name": "laptop",
                        "workloads": ".*",
                        "job_records_path": str(tmp_path / "jobs"),
                        "env": env,
                        "threads": 2,
                    }
                ]
            }
        }
    )
    return ExecutionPolicy(rc).resolve(ExecutionRequest(workload="transform"))


@pytest.fixture
def spec(tmp_path):
    return make_spec(tmp_path, {"SITE": "it's here"})


# Identity and contents


def test_records_are_created_once_per_key(spec, tmp_path):
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    assert record.path == tmp_path / "jobs" / "job-1"
    with pytest.raises(FileExistsError):
        JobRecord.create(spec, key="job-1", command=COMMAND)


def test_an_opened_record_keeps_its_spec_and_command(spec):
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    opened = JobRecord.open(record.path)
    assert opened.key == "job-1"
    assert opened.spec == spec
    assert opened.command == COMMAND
    assert opened.created_at == record.created_at
    assert opened.receipt is None


@pytest.mark.parametrize(
    ("key", "command"), [("../job", COMMAND), (".hidden", COMMAND), ("job", [])]
)
def test_records_reject_unsafe_keys_and_empty_commands(spec, key, command):
    with pytest.raises(ValueError):
        JobRecord.create(spec, key=key, command=command)


def test_opening_a_directory_without_a_record_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        JobRecord.open(tmp_path)


def test_job_script_runs_the_command_with_the_job_environment(spec):
    command = [sys.executable, "-c", "import os; print(os.environ['SITE'])"]
    record = JobRecord.create(spec, key="job-1", command=command)
    script = record.path / JobRecord.script_filename
    result = subprocess.run(  # noqa: S603
        ["/bin/sh", str(script)], capture_output=True, text=True, check=True
    )
    assert result.stdout == "it's here\n"
    assert record.read_exit_status() == 0


def test_added_environment_overrides_the_job_spec(spec):
    command = [sys.executable, "-c", "import os; print(os.environ['SITE'])"]
    record = JobRecord.create(
        spec, key="job-1", command=command, env={"SITE": "elsewhere"}
    )
    assert JobRecord.open(record.path).env == {"SITE": "elsewhere"}
    script = record.path / JobRecord.script_filename
    result = subprocess.run(  # noqa: S603
        ["/bin/sh", str(script)], capture_output=True, text=True, check=True
    )
    assert result.stdout == "elsewhere\n"


def test_job_script_records_a_failing_exit_status(spec):
    record = JobRecord.create(
        spec, key="job-1", command=[sys.executable, "-c", "raise SystemExit(3)"]
    )
    script = record.path / JobRecord.script_filename
    result = subprocess.run(["/bin/sh", str(script)], check=False)  # noqa: S603
    assert result.returncode == 3
    assert record.read_exit_status() == 3


def test_environment_names_must_be_shell_identifiers(tmp_path):
    spec = make_spec(tmp_path, {"A-B": "1"})
    with pytest.raises(ValueError, match="shell identifiers"):
        JobRecord.create(spec, key="job-1", command=COMMAND)


# Once-only submission


def test_repeated_submission_returns_the_first_receipt(spec):
    scheduler = RecordingScheduler()
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    first = record.submit(scheduler)
    assert record.submit(scheduler) == first
    assert JobRecord.open(record.path).submit(scheduler) == first
    assert scheduler.submitted == ["job-1"]


def test_concurrent_submissions_submit_once(spec):
    scheduler = RecordingScheduler()
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    outcomes = []

    def submit():
        try:
            outcomes.append(JobRecord.open(record.path).submit(scheduler))
        except SubmissionUnresolvedError as error:
            outcomes.append(error)

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert scheduler.submitted == ["job-1"]
    assert record.receipt in outcomes


def test_a_failed_submission_leaves_the_record_unresolved(spec):
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    with pytest.raises(OSError, match="lost"):
        record.submit(RecordingScheduler(error=OSError("lost")))
    assert record.is_unresolved
    scheduler = RecordingScheduler()
    with pytest.raises(SubmissionUnresolvedError):
        record.submit(scheduler)
    with pytest.raises(SubmissionUnresolvedError):
        record.status(scheduler)
    assert scheduler.submitted == []


# Reconciliation


def make_unresolved(spec):
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    intent = record.path / JobRecord.intent_filename
    intent.write_text(
        f"host: elsewhere\npid: 1\ntime: {datetime.now(UTC).isoformat()}\n"
    )
    return record


def test_reconciliation_records_the_job_found(spec):
    record = make_unresolved(spec)
    found = SubmissionReceipt(native_id="77")
    assert record.reconcile(RecordingScheduler(found=[found])) == found
    assert record.receipt == found
    assert not record.is_unresolved


def test_reconciliation_without_a_job_allows_submission_again(spec):
    record = make_unresolved(spec)
    scheduler = RecordingScheduler()
    assert record.reconcile(scheduler) is None
    assert not record.is_unresolved
    assert record.submit(scheduler).native_id == "101"


def test_reconciliation_rejects_several_jobs_with_the_key(spec):
    record = make_unresolved(spec)
    found = [SubmissionReceipt(native_id="77"), SubmissionReceipt(native_id="78")]
    with pytest.raises(SubmissionUnresolvedError, match="Several jobs"):
        record.reconcile(RecordingScheduler(found=found))
    assert record.is_unresolved


def test_reconciliation_waits_for_a_live_submitter(spec):
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    with pytest.raises(OSError, match="lost"):
        record.submit(RecordingScheduler(error=OSError("lost")))
    with pytest.raises(SubmissionUnresolvedError, match="in progress"):
        record.reconcile(RecordingScheduler())


def test_reconciliation_of_a_submitted_record_returns_its_receipt(spec):
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    receipt = record.submit(RecordingScheduler())
    assert record.reconcile(RecordingScheduler(found=[])) == receipt


# Observation and cancellation


def test_status_history_records_each_change_once(spec):
    queued = JobStatus(state=JobState.queued)
    running = JobStatus(state=JobState.running)
    done = JobStatus(state=JobState.completed, exit_code=0, native_state="COMPLETED")
    scheduler = RecordingScheduler(statuses=[queued, queued, running, done, done])
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    record.submit(scheduler)
    observed = [record.status(scheduler) for _ in range(5)]
    assert observed[-1] == done
    history = JobRecord.open(record.path).history
    assert [status.state for status in history] == ["queued", "running", "completed"]
    assert history[-1] == done


def test_states_report_whether_the_job_finished():
    assert {state for state in JobState if state.is_terminal} == {
        JobState.completed,
        JobState.failed,
        JobState.canceled,
    }


def test_cancellation_is_recorded_before_the_scheduler_is_asked(spec):
    scheduler = RecordingScheduler()
    record = JobRecord.create(spec, key="job-1", command=COMMAND)
    with pytest.raises(ValueError, match="not been submitted"):
        record.cancel(scheduler)
    receipt = record.submit(scheduler)
    record.cancel(scheduler)
    assert JobRecord.open(record.path).cancel_requested
    assert scheduler.canceled == [receipt.native_id]
