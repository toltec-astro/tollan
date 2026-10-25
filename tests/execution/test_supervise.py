"""Supervision waits for a job's outcome without changing the job."""

import sys

import pytest

from tollan.config import RuntimeContext
from tollan.execution import (
    ExecutionPolicy,
    ExecutionRequest,
    JobRecord,
    JobState,
    JobStatus,
    LocalScheduler,
    SupervisionOutcomeKind,
    TransportError,
    cancel_job,
    supervise_job,
)

from .schedulers import RecordingScheduler

QUEUED = JobStatus(state=JobState.queued)
RUNNING = JobStatus(state=JobState.running)
UNKNOWN = JobStatus(state=JobState.unknown)
COMPLETED = JobStatus(state=JobState.completed, exit_code=0, native_state="done")


@pytest.fixture
def record(tmp_path):
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
                    }
                ]
            }
        }
    )
    spec = ExecutionPolicy(rc).resolve(ExecutionRequest(workload="transform"))
    return JobRecord.create(spec, key="job-1", command=[sys.executable, "-c", "1"])


def supervise(record, statuses, **kwargs):
    scheduler = RecordingScheduler(statuses=statuses)
    record.submit(scheduler)
    outcome = supervise_job(
        record, scheduler, poll_interval=0.01, unknown_grace=0.1, **kwargs
    )
    return outcome, scheduler


def test_a_completed_job_with_exit_status_zero_succeeds(record):
    observed = []
    outcome, _ = supervise(
        record, [QUEUED, RUNNING, RUNNING, COMPLETED], on_status=observed.append
    )
    assert outcome.kind == SupervisionOutcomeKind.succeeded
    assert outcome.status == COMPLETED
    assert [status.state for status in observed] == ["queued", "running", "completed"]


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (JobStatus(state=JobState.completed, exit_code=1), "failed"),
        (JobStatus(state=JobState.completed), "failed"),
        (JobStatus(state=JobState.failed, exit_code=0), "failed"),
        (JobStatus(state=JobState.canceled), "canceled"),
    ],
)
def test_other_terminal_states_do_not_succeed(record, status, kind):
    outcome, _ = supervise(record, [RUNNING, status])
    assert outcome.kind == kind
    assert outcome.status == status


def test_the_result_check_decides_a_completed_job(record):
    checked = []

    def reject(checked_record):
        checked.append(checked_record.key)
        return False

    outcome, _ = supervise(record, [COMPLETED], check=reject)
    assert outcome.kind == SupervisionOutcomeKind.failed
    assert "result check failed" in outcome.message
    assert checked == ["job-1"]
    outcome, _ = supervise(JobRecord.open(record.path), [COMPLETED], check=bool)
    assert outcome.kind == SupervisionOutcomeKind.succeeded


def test_an_unknown_state_beyond_the_grace_period_is_unresolved(record):
    outcome, scheduler = supervise(record, [RUNNING, UNKNOWN])
    assert outcome.kind == SupervisionOutcomeKind.unresolved
    assert outcome.status == UNKNOWN
    assert scheduler.submitted == ["job-1"]
    assert scheduler.canceled == []
    assert record.receipt is not None


def test_an_unknown_state_within_the_grace_period_is_tolerated(record):
    outcome, _ = supervise(record, [UNKNOWN, UNKNOWN, RUNNING, UNKNOWN, COMPLETED])
    assert outcome.kind == SupervisionOutcomeKind.succeeded


def test_an_unreachable_scheduler_is_not_a_job_state(record):
    lost = TransportError("ssh to login failed")
    outcome, _ = supervise(record, [RUNNING, lost, COMPLETED])
    assert outcome.kind == SupervisionOutcomeKind.succeeded
    assert [status.state for status in record.history] == ["running", "completed"]
    outcome, _ = supervise(JobRecord.open(record.path), [lost])
    assert outcome.kind == SupervisionOutcomeKind.unresolved
    assert "ssh to login failed" in outcome.message


def test_cancellation_reports_an_unconfirmed_request(record):
    scheduler = RecordingScheduler(statuses=[RUNNING])
    receipt = record.submit(scheduler)
    outcome = cancel_job(record, scheduler, timeout=0.05, poll_interval=0.01)
    assert outcome.kind == SupervisionOutcomeKind.cancel_requested
    assert outcome.status == RUNNING
    assert scheduler.canceled == [receipt.native_id]
    assert record.cancel_requested


def test_stopping_the_supervisor_leaves_a_local_job_running(tmp_path, record):
    command = [sys.executable, "-c", "import time; time.sleep(1)"]
    job = JobRecord.create(record.spec, key="job-2", command=command)
    scheduler = LocalScheduler()
    job.submit(scheduler)

    def stop(status):
        if status.state == JobState.running:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        supervise_job(job, scheduler, poll_interval=0.01, on_status=stop)
    reopened = JobRecord.open(job.path)
    assert reopened.status(scheduler).state == JobState.running
    outcome = supervise_job(reopened, scheduler, poll_interval=0.05)
    assert outcome.kind == SupervisionOutcomeKind.succeeded


def test_canceling_a_local_job_confirms_its_termination(record):
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    job = JobRecord.create(record.spec, key="job-2", command=command)
    scheduler = LocalScheduler()
    job.submit(scheduler)
    outcome = cancel_job(job, scheduler, timeout=20, poll_interval=0.05)
    assert outcome.kind == SupervisionOutcomeKind.canceled
    assert outcome.status is not None
    assert outcome.status.state == JobState.canceled
