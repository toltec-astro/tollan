"""Schedulers that submit, observe and cancel the jobs of job records."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import astropy.units as u

from .job import JobState, JobStatus, SubmissionReceipt
from .policy import LocalProfile, SlurmProfile
from .transport import LocalTransport, SshTransport

if TYPE_CHECKING:
    from .job import JobRecord, Scheduler
    from .policy import ExecutionProfile
    from .transport import Transport

__all__ = ["LocalScheduler", "SlurmScheduler", "get_scheduler"]

# Start the job script in its own session from a short-lived intermediate
# process, so the job outlives its submitter and is reaped by the system.
_DETACH = """
import subprocess, sys
script, output = sys.argv[1:]
with open(output, "ab") as stream:
    process = subprocess.Popen(
        ["/bin/sh", script],
        stdin=subprocess.DEVNULL,
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
print(process.pid)
"""


def _leads_live_group(pid: int) -> bool:
    try:
        return os.getpgid(pid) == pid
    except ProcessLookupError:
        return False


class LocalScheduler:
    """Run jobs as detached processes on this host.

    The job script runs in its own session and continues when the submitting
    process exits. Its native ID is the script's process ID. Any process on the
    same host can observe or cancel the job through its record.
    """

    def submit(self, record: JobRecord) -> SubmissionReceipt:
        """Start the record's job script.

        Parameters
        ----------
        record : JobRecord
            Record whose job to start.

        Returns
        -------
        SubmissionReceipt
            Receipt with the process ID of the job script.
        """
        result = subprocess.run(  # noqa: S603 -- Fixed interpreter and arguments.
            [
                sys.executable,
                "-c",
                _DETACH,
                str(record.path / record.script_filename),
                str(record.path / record.output_filename),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return SubmissionReceipt(native_id=result.stdout.strip())

    def get_status(self, record: JobRecord, receipt: SubmissionReceipt) -> JobStatus:
        """Return the status of a local job.

        Parameters
        ----------
        record : JobRecord
            Record of the job.
        receipt : SubmissionReceipt
            Receipt of the job.

        Returns
        -------
        JobStatus
            ``completed`` or ``failed`` with the recorded exit status;
            ``running`` while the process runs; otherwise ``canceled`` after a
            cancellation request, else ``failed`` without an exit status.
        """
        running = _leads_live_group(int(receipt.native_id))
        exit_code = record.read_exit_status()
        if exit_code is not None:
            state = JobState.completed if exit_code == 0 else JobState.failed
            return JobStatus(state=state, exit_code=exit_code, native_state="exited")
        if running:
            return JobStatus(state=JobState.running, native_state="running")
        state = JobState.canceled if record.cancel_requested else JobState.failed
        return JobStatus(state=state, native_state="terminated")

    def find(self, record: JobRecord, since: datetime) -> list[SubmissionReceipt]:
        """Return the job started from the record since a time.

        Parameters
        ----------
        record : JobRecord
            Record of the job.
        since : datetime.datetime
            Start of the submission.

        Returns
        -------
        list of SubmissionReceipt
            The job whose script recorded its process ID since ``since``; empty
            when no job script started.
        """
        path = record.path / record.pid_filename
        if not path.exists():
            return []
        started = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if started < since.replace(microsecond=0):
            return []
        return [SubmissionReceipt(native_id=path.read_text().strip(), time=started)]

    def cancel(self, record: JobRecord, receipt: SubmissionReceipt) -> None:
        """Send SIGTERM to the job's process group.

        Parameters
        ----------
        record : JobRecord
            Record of the job.
        receipt : SubmissionReceipt
            Receipt of the job.
        """
        pid = int(receipt.native_id)
        if _leads_live_group(pid):
            with suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGTERM)


_SLURM_STATES = {
    JobState.queued: {"PENDING", "REQUEUED", "CONFIGURING"},
    JobState.running: {"RUNNING", "COMPLETING", "SUSPENDED", "RESIZING"},
    JobState.completed: {"COMPLETED"},
    JobState.canceled: {"CANCELLED"},
    JobState.failed: {
        "FAILED",
        "TIMEOUT",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "BOOT_FAIL",
        "DEADLINE",
        "PREEMPTED",
    },
}
_SLURM_STATE_MAP = {
    native: state for state, natives in _SLURM_STATES.items() for native in natives
}
# sacct interprets times in the submission host's time zone; a one-day margin
# keeps every zone inside the search window, which the working directory narrows.
_SEARCH_MARGIN = timedelta(days=1)


def _slurm_status(native_state: str, exit_code: str | None) -> JobStatus:
    # States such as "CANCELLED by 1234" carry details after the first word.
    native = native_state.split(maxsplit=1)[0] if native_state.strip() else ""
    state = _SLURM_STATE_MAP.get(native, JobState.unknown)
    code = None
    if state.is_terminal and exit_code:
        code = int(exit_code.split(":")[0])
    return JobStatus(state=state, exit_code=code, native_state=native or None)


def _rows(output: str) -> list[list[str]]:
    return [line.split("|") for line in output.splitlines() if "|" in line]


class SlurmScheduler:
    """Submit, observe and cancel jobs through Slurm commands.

    Commands run on the submission host through a transport. The job name is
    the record key and the working directory is the record directory, which
    together identify the job during reconciliation.

    Parameters
    ----------
    transport : Transport
        Runs ``sbatch``, ``sacct``, ``squeue``, ``sinfo`` and ``scancel`` on the
        submission host.
    """

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def submit(self, record: JobRecord) -> SubmissionReceipt:
        """Submit the record's job script with ``sbatch``.

        Parameters
        ----------
        record : JobRecord
            Record of a job resolved with a Slurm profile.

        Returns
        -------
        SubmissionReceipt
            Receipt with the Slurm job ID and, when reported, the cluster.

        Raises
        ------
        ValueError
            No node of the partition is selected for the job.
        """
        profile = self._profile(record)
        resources = profile.get_resources(record.spec.request)
        args = [
            "sbatch",
            "--parsable",
            "--no-requeue",
            f"--job-name={record.key}",
            f"--chdir={record.path}",
            f"--output={record.path / record.output_filename}",
            "--nodes=1",
            "--ntasks=1",
            f"--partition={profile.partition}",
        ]
        if profile.account is not None:
            args.append(f"--account={profile.account}")
        if profile.qos is not None:
            args.append(f"--qos={profile.qos}")
        args += [
            f"--cpus-per-task={resources.cpus}",
            f"--mem={math.ceil(resources.memory.to_value(u.MiB))}M",
            f"--time={math.ceil(resources.time_limit.to_value(u.min))}",
        ]
        excluded = self._excluded_nodes(record, profile)
        if excluded:
            args.append("--exclude=" + ",".join(excluded))
        args.append(str(record.path / record.script_filename))
        native_id, _, cluster = self.transport.run(args).strip().partition(";")
        return SubmissionReceipt(native_id=native_id, cluster=cluster or None)

    def get_status(self, record: JobRecord, receipt: SubmissionReceipt) -> JobStatus:
        """Return the status of a Slurm job from accounting or the queue.

        Parameters
        ----------
        record : JobRecord
            Record of the job.
        receipt : SubmissionReceipt
            Receipt of the job.

        Returns
        -------
        JobStatus
            Status mapped from the Slurm state; ``unknown`` when neither
            accounting nor the queue reports the job.
        """
        rows = _rows(
            self.transport.run(
                [
                    "sacct",
                    "-X",
                    "-n",
                    "-P",
                    *self._cluster_args(receipt),
                    "-j",
                    receipt.native_id,
                    "--format=JobIDRaw,State,ExitCode",
                ]
            )
        )
        for job_id, native_state, exit_code, *_ in rows:
            if job_id == receipt.native_id:
                return _slurm_status(native_state, exit_code)
        for job_id, native_state, *_ in self._queue(record, "%i|%T"):
            if job_id == receipt.native_id:
                return _slurm_status(native_state, None)
        return JobStatus(state=JobState.unknown)

    def find(self, record: JobRecord, since: datetime) -> list[SubmissionReceipt]:
        """Return jobs named by the record key and run in the record directory.

        Parameters
        ----------
        record : JobRecord
            Record of the job.
        since : datetime.datetime
            Start of the submission.

        Returns
        -------
        list of SubmissionReceipt
            Matching jobs from the queue and from accounting.
        """
        start = (since - _SEARCH_MARGIN).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        accounted = _rows(
            self.transport.run(
                [
                    "sacct",
                    "-X",
                    "-n",
                    "-P",
                    f"--name={record.key}",
                    f"--starttime={start}",
                    "--format=JobIDRaw,WorkDir",
                ]
            )
        )
        found: dict[str, None] = {}
        for job_id, work_dir, *_ in [*self._queue(record, "%i|%Z"), *accounted]:
            if work_dir == str(record.path):
                found[job_id] = None
        return [SubmissionReceipt(native_id=job_id) for job_id in found]

    def cancel(self, record: JobRecord, receipt: SubmissionReceipt) -> None:
        """Request cancellation with ``scancel``.

        Parameters
        ----------
        record : JobRecord
            Record of the job.
        receipt : SubmissionReceipt
            Receipt of the job.
        """
        self.transport.run(["scancel", *self._cluster_args(receipt), receipt.native_id])

    @staticmethod
    def _profile(record: JobRecord) -> SlurmProfile:
        profile = record.spec.profile
        if not isinstance(profile, SlurmProfile):
            msg = f"Job {record.key!r} was not resolved with a Slurm profile"
            raise TypeError(msg)
        return profile

    @staticmethod
    def _cluster_args(receipt: SubmissionReceipt) -> list[str]:
        return [] if receipt.cluster is None else [f"--clusters={receipt.cluster}"]

    def _queue(self, record: JobRecord, fields: str) -> list[list[str]]:
        return _rows(
            self.transport.run(
                ["squeue", "-h", f"--name={record.key}", f"--format={fields}"]
            )
        )

    def _excluded_nodes(self, record: JobRecord, profile: SlurmProfile) -> list[str]:
        request = record.spec.request
        if request.nodes is None and profile.nodes.model_dump() == {"excludes": []}:
            return []
        output = self.transport.run(
            ["sinfo", "-h", "-N", f"--partition={profile.partition}", "--format=%N"]
        )
        nodes = list(dict.fromkeys(output.split()))
        selected = set(profile.select_nodes(request, nodes))
        if not selected:
            msg = (
                f"No node of partition {profile.partition!r} is selected for "
                f"{record.key!r}"
            )
            raise ValueError(msg)
        return [node for node in nodes if node not in selected]


def get_scheduler(profile: ExecutionProfile) -> Scheduler:
    """Return the scheduler for jobs of an execution profile.

    Parameters
    ----------
    profile : LocalProfile or SlurmProfile
        Profile of the jobs.

    Returns
    -------
    Scheduler
        `LocalScheduler` for a local profile; `SlurmScheduler` for a Slurm
        profile, reaching its ``host`` over SSH or running on this host when
        ``host`` is None.
    """
    if isinstance(profile, LocalProfile):
        return LocalScheduler()
    transport = LocalTransport() if profile.host is None else SshTransport(profile.host)
    return SlurmScheduler(transport)
