"""The local scheduler runs detached jobs that any local process can follow."""

import os
import subprocess
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

SCHEDULER = LocalScheduler()


def python(code):
    return [sys.executable, "-c", code]


@pytest.fixture
def spec(tmp_path):
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
                        "env": {"GREETING": "hello"},
                        "threads": 2,
                    }
                ]
            }
        }
    )
    return ExecutionPolicy(rc).resolve(ExecutionRequest(workload="transform"))


def wait_until(record, states, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = record.status(SCHEDULER)
        if status.state in states:
            return status
        time.sleep(0.05)
    msg = f"Job {record.key} did not reach {states}"
    raise TimeoutError(msg)


def output(record):
    return (record.path / JobRecord.output_filename).read_text()


def test_a_successful_job_completes_with_its_output_and_environment(spec):
    code = "import os; print(os.environ['GREETING'], os.environ['OMP_NUM_THREADS'])"
    record = JobRecord.create(spec, key="job-1", command=python(code))
    record.submit(SCHEDULER)
    status = wait_until(record, {JobState.completed, JobState.failed})
    assert status.state == JobState.completed
    assert status.exit_code == 0
    assert output(record) == "hello 2\n"


def test_a_failing_job_reports_its_exit_status(spec):
    record = JobRecord.create(spec, key="job-1", command=python("raise SystemExit(3)"))
    record.submit(SCHEDULER)
    status = wait_until(record, {JobState.completed, JobState.failed})
    assert (status.state, status.exit_code) == (JobState.failed, 3)


def test_a_canceled_job_stops_and_reports_cancellation(spec):
    record = JobRecord.create(
        spec, key="job-1", command=python("import time; time.sleep(60)")
    )
    receipt = record.submit(SCHEDULER)
    assert wait_until(record, {JobState.running}).state == JobState.running
    record.cancel(SCHEDULER)
    status = wait_until(record, {JobState.canceled, JobState.failed})
    assert status.state == JobState.canceled
    assert status.exit_code is None
    with pytest.raises(ProcessLookupError):
        os.killpg(int(receipt.native_id), 0)


def test_another_process_follows_a_job_it_did_not_submit(spec):
    record = JobRecord.create(
        spec, key="job-1", command=python("import time; time.sleep(0.5)")
    )
    submitter = (
        "import sys; from tollan.execution import JobRecord, LocalScheduler; "
        "JobRecord.open(sys.argv[1]).submit(LocalScheduler())"
    )
    subprocess.run(  # noqa: S603
        [*python(submitter), str(record.path)], check=True
    )
    observer = (
        "import sys, time; from tollan.execution import JobRecord, LocalScheduler; "
        "record = JobRecord.open(sys.argv[1]); scheduler = LocalScheduler()\n"
        "while not (status := record.status(scheduler)).state.is_terminal:\n"
        "    time.sleep(0.05)\n"
        "print(status.state, status.exit_code)"
    )
    result = subprocess.run(  # noqa: S603
        [*python(observer), str(record.path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert result.stdout == "completed 0\n"
    assert [s.state for s in record.history][-1] == JobState.completed


def test_reconciliation_finds_a_started_job_without_a_receipt(spec):
    record = JobRecord.create(spec, key="job-1", command=python("pass"))
    receipt = record.submit(SCHEDULER)
    wait_until(record, {JobState.completed})
    # The submitter stopped after starting the job, before writing the receipt.
    (record.path / JobRecord.receipt_filename).unlink()
    intent = record.path / JobRecord.intent_filename
    intent.write_text(intent.read_text().replace("host: ", "host: elsewhere-"))
    found = record.reconcile(SCHEDULER)
    assert found is not None
    assert found.native_id == receipt.native_id


def test_reconciliation_without_a_started_job_allows_submission(spec):
    record = JobRecord.create(spec, key="job-1", command=python("pass"))
    intent = record.path / JobRecord.intent_filename
    intent.write_text("host: elsewhere\npid: 1\ntime: 2026-01-01T00:00:00+00:00\n")
    assert record.reconcile(SCHEDULER) is None
    record.submit(SCHEDULER)
    assert wait_until(record, {JobState.completed}).exit_code == 0
