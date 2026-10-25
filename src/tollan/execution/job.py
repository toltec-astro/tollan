"""Job records: the durable state of one external job.

A job record is a directory beneath its profile's ``job_records_path``. Any
process with access to it can submit, observe, reattach to or cancel the job.
Submission is once-only: a repeated submission returns the existing receipt, and
a submission that began without producing a receipt must be reconciled before
the job can be submitted again.
"""

from __future__ import annotations

import os
import re
import shlex
import socket
from datetime import UTC, datetime
from enum import StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Protocol, Self

from pydantic import AwareDatetime, Field

from tollan.config import FrozenBaseModel
from tollan.config.types import SafeName

from .policy import JobSpec

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "JobRecord",
    "JobState",
    "JobStatus",
    "Scheduler",
    "SubmissionReceipt",
    "SubmissionUnresolvedError",
]

type _Time = Annotated[AwareDatetime, Field(strict=False)]

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _now() -> datetime:
    return datetime.now(UTC)


class JobState(StrEnum):
    """State of a job as reported by its scheduler."""

    #: Submitted and waiting to start.
    queued = auto()
    #: Started and not yet finished.
    running = auto()
    #: Finished as reported complete by the scheduler.
    completed = auto()
    #: Finished unsuccessfully.
    failed = auto()
    #: Finished by cancellation.
    canceled = auto()
    #: The scheduler has no information about the job.
    unknown = auto()

    @property
    def is_terminal(self) -> bool:
        """Whether the job has finished."""
        return self in {JobState.completed, JobState.failed, JobState.canceled}


class JobStatus(FrozenBaseModel):
    """One observation of a job's state.

    Attributes
    ----------
    state : JobState
        State of the job.
    exit_code : int or None
        Exit status of the external process, when the scheduler reports one.
    native_state : str or None
        State as the scheduler reports it, such as ``"OUT_OF_MEMORY"``.
    time : datetime.datetime
        Time of the observation.
    """

    state: JobState = Field(strict=False)
    exit_code: int | None = None
    native_state: str | None = None
    time: _Time = Field(default_factory=_now)

    def same_as(self, other: JobStatus) -> bool:
        """Whether two observations agree apart from their time.

        Parameters
        ----------
        other : JobStatus
            Another observation.

        Returns
        -------
        bool
            True when state, exit code and native state are equal.
        """
        return (self.state, self.exit_code, self.native_state) == (
            other.state,
            other.exit_code,
            other.native_state,
        )


class SubmissionReceipt(FrozenBaseModel):
    """Scheduler acknowledgement of a submitted job.

    Attributes
    ----------
    native_id : str
        Job identifier assigned by the scheduler.
    cluster : str or None
        Cluster that accepted the job, when the scheduler reports one.
    time : datetime.datetime
        Time of the submission.
    """

    native_id: str
    cluster: SafeName | None = None
    time: _Time = Field(default_factory=_now)


class _ProcessStamp(FrozenBaseModel):
    """Host, process and time of an action on a record."""

    host: str = Field(default_factory=socket.gethostname)
    pid: int = Field(default_factory=os.getpid)
    time: _Time = Field(default_factory=_now)

    def is_live_here(self) -> bool:
        """Whether the stamped process still runs on this host."""
        if self.host != socket.gethostname():
            return False
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


class _JobFile(FrozenBaseModel):
    """Contents of a record's ``job.yaml``."""

    key: SafeName
    spec: JobSpec
    command: Annotated[list[str], Field(min_length=1)]
    env: dict[str, str]
    created_at: _Time


class SubmissionUnresolvedError(RuntimeError):
    """A submission began without producing a receipt; reconcile the record."""


class Scheduler(Protocol):
    """Operations a scheduler provides for job records."""

    def submit(self, record: JobRecord) -> SubmissionReceipt:
        """Submit the record's job script and return the scheduler's receipt."""
        ...

    def get_status(self, record: JobRecord, receipt: SubmissionReceipt) -> JobStatus:
        """Return the current status of a submitted job."""
        ...

    def find(self, record: JobRecord, since: datetime) -> list[SubmissionReceipt]:
        """Return jobs carrying the record's key submitted since a time."""
        ...

    def cancel(self, record: JobRecord, receipt: SubmissionReceipt) -> None:
        """Request termination of a submitted job."""
        ...


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text)
    temporary.replace(path)


def _job_script(path: Path, command: Sequence[str], env: dict[str, str]) -> str:
    invalid = sorted(name for name in env if not _ENV_NAME.fullmatch(name))
    if invalid:
        msg = f"Environment variable names must be shell identifiers: {invalid}"
        raise ValueError(msg)
    return "\n".join(
        [
            "#!/bin/sh",
            f"cd {shlex.quote(str(path))} || exit 1",
            'printf "%s\\n" "$$" > pid',
            *(f"export {name}={shlex.quote(value)}" for name, value in env.items()),
            shlex.join(command),
            "status=$?",
            'printf "%s\\n" "$status" > exit_status.tmp',
            "mv exit_status.tmp exit_status",
            'exit "$status"',
            "",
        ]
    )


class JobRecord:
    """Durable state of one job in its record directory.

    Create a record with `create` and open an existing one with `open`; do not
    construct it directly.
    """

    #: Job spec, key, command and creation time.
    job_filename = "job.yaml"
    #: Script that exports the environment, runs the command and records its exit.
    script_filename = "job.sh"
    #: Submission intent: host, process and time of the submitting process.
    intent_filename = "submit.yaml"
    #: Submission receipt.
    receipt_filename = "receipt.yaml"
    #: Observed status history, one JSON object per line.
    history_filename = "status.jsonl"
    #: Cancellation request.
    cancel_filename = "cancel.yaml"
    #: Exit status written by the job script.
    exit_status_filename = "exit_status"
    #: Combined standard output and error of the job.
    output_filename = "output.log"
    #: Process ID of the job script on the host that runs it.
    pid_filename = "pid"

    def __init__(self, path: Path, job: _JobFile) -> None:
        self._path = path
        self._job = job

    @classmethod
    def create(
        cls,
        spec: JobSpec,
        *,
        key: str,
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
    ) -> Self:
        """Create a job record beneath the profile's ``job_records_path``.

        Parameters
        ----------
        spec : JobSpec
            Job spec resolved for the job.
        key : str
            Name of the record, unique within ``job_records_path``; a
            `~tollan.config.types.SafeName`. Batch schedulers use it as the job
            name.
        command : sequence of str
            Program and arguments of the external process.
        env : mapping of str to str or None
            Environment variables of the external process in addition to those
            of the job spec, which they override. Default is None.

        Returns
        -------
        JobRecord
            The new record, not yet submitted.

        Raises
        ------
        FileExistsError
            A record with this key exists.
        ValueError
            The key or command is invalid, or an environment variable name is
            not a shell identifier.
        """
        job = _JobFile(
            key=key,
            spec=spec,
            command=list(command),
            env=dict(env or {}),
            created_at=_now(),
        )
        root = Path(str(spec.profile.job_records_path))
        path = root / job.key
        script = _job_script(path, job.command, spec.as_environ() | job.env)
        root.mkdir(parents=True, exist_ok=True)
        path.mkdir()
        (path / cls.script_filename).write_text(script)
        _write_atomic(path / cls.job_filename, job.model_dump_yaml(mode="json"))
        return cls(path, job)

    @classmethod
    def open(cls, path: str | os.PathLike[str]) -> Self:
        """Open an existing job record.

        Parameters
        ----------
        path : str or os.PathLike
            Record directory.

        Returns
        -------
        JobRecord
            The record, in whatever state other processes left it.

        Raises
        ------
        FileNotFoundError
            The directory holds no job record.
        """
        path = Path(path)
        return cls(path, _JobFile.model_validate_yaml(path / cls.job_filename))

    @property
    def path(self) -> Path:
        """Record directory."""
        return self._path

    @property
    def key(self) -> str:
        """Name of the record within its ``job_records_path``."""
        return self._job.key

    @property
    def spec(self) -> JobSpec:
        """Job spec the record was created with."""
        return self._job.spec

    @property
    def command(self) -> list[str]:
        """Program and arguments of the external process."""
        return list(self._job.command)

    @property
    def env(self) -> dict[str, str]:
        """Environment variables added to those of the job spec."""
        return dict(self._job.env)

    @property
    def created_at(self) -> datetime:
        """Creation time of the record."""
        return self._job.created_at

    @property
    def receipt(self) -> SubmissionReceipt | None:
        """Submission receipt; None until submission succeeds."""
        path = self._path / self.receipt_filename
        if not path.exists():
            return None
        return SubmissionReceipt.model_validate_yaml(path)

    @property
    def is_unresolved(self) -> bool:
        """Whether a submission began without producing a receipt."""
        return (self._path / self.intent_filename).exists() and self.receipt is None

    @property
    def cancel_requested(self) -> bool:
        """Whether cancellation of the job has been requested."""
        return (self._path / self.cancel_filename).exists()

    @property
    def history(self) -> list[JobStatus]:
        """Observed statuses, oldest first, recording each change once."""
        path = self._path / self.history_filename
        if not path.exists():
            return []
        lines = path.read_text().split("\n")
        # A line without its newline is still being written.
        return [JobStatus.model_validate_json(line) for line in lines[:-1] if line]

    def submit(self, scheduler: Scheduler) -> SubmissionReceipt:
        """Submit the job once.

        Parameters
        ----------
        scheduler : Scheduler
            Scheduler of the record's profile kind.

        Returns
        -------
        SubmissionReceipt
            The receipt of this or an earlier submission.

        Raises
        ------
        SubmissionUnresolvedError
            A submission began without producing a receipt, possibly in another
            process. Use `reconcile` once no submission is in progress.
        """
        receipt = self.receipt
        if receipt is not None:
            return receipt
        intent = _ProcessStamp()
        try:
            with (self._path / self.intent_filename).open("x") as stream:
                stream.write(intent.model_dump_yaml(mode="json"))
        except FileExistsError:
            receipt = self.receipt
            if receipt is not None:
                return receipt
            msg = f"Submission of job {self.key!r} began without a receipt; reconcile"
            raise SubmissionUnresolvedError(msg) from None
        receipt = scheduler.submit(self)
        self._write_receipt(receipt)
        return receipt

    def reconcile(self, scheduler: Scheduler) -> SubmissionReceipt | None:
        """Resolve a submission that began without producing a receipt.

        Parameters
        ----------
        scheduler : Scheduler
            Scheduler of the record's profile kind.

        Returns
        -------
        SubmissionReceipt or None
            The receipt of the job found, or of an earlier successful
            submission. None when no job was submitted; the record can then be
            submitted again.

        Raises
        ------
        SubmissionUnresolvedError
            The submitting process still runs on this host, or the scheduler
            reports several jobs carrying the key.
        """
        receipt = self.receipt
        intent_path = self._path / self.intent_filename
        if receipt is not None or not intent_path.exists():
            return receipt
        intent = _ProcessStamp.model_validate_yaml(intent_path)
        if intent.is_live_here():
            msg = f"Submission of job {self.key!r} is in progress (PID {intent.pid})"
            raise SubmissionUnresolvedError(msg)
        found = scheduler.find(self, intent.time)
        if len(found) > 1:
            ids = [item.native_id for item in found]
            msg = f"Several jobs carry key {self.key!r}: {ids}"
            raise SubmissionUnresolvedError(msg)
        if not found:
            intent_path.unlink()
            return None
        self._write_receipt(found[0])
        return found[0]

    def status(self, scheduler: Scheduler) -> JobStatus:
        """Observe the job's current status and record any change.

        Parameters
        ----------
        scheduler : Scheduler
            Scheduler of the record's profile kind.

        Returns
        -------
        JobStatus
            Current status reported by the scheduler.

        Raises
        ------
        SubmissionUnresolvedError
            A submission began without producing a receipt.
        ValueError
            The job has not been submitted.
        """
        status = scheduler.get_status(self, self._require_receipt())
        history = self.history
        if not history or not history[-1].same_as(status):
            with (self._path / self.history_filename).open("a") as stream:
                stream.write(status.model_dump_json() + "\n")
        return status

    def cancel(self, scheduler: Scheduler) -> None:
        """Request cancellation of the job.

        The request is recorded before the scheduler is asked to terminate the
        job. Confirming a terminal state is left to the caller.

        Parameters
        ----------
        scheduler : Scheduler
            Scheduler of the record's profile kind.

        Raises
        ------
        SubmissionUnresolvedError
            A submission began without producing a receipt.
        ValueError
            The job has not been submitted.
        """
        receipt = self._require_receipt()
        if not self.cancel_requested:
            _write_atomic(
                self._path / self.cancel_filename,
                _ProcessStamp().model_dump_yaml(mode="json"),
            )
        scheduler.cancel(self, receipt)

    def read_exit_status(self) -> int | None:
        """Return the exit status written by the job script, if any.

        Returns
        -------
        int or None
            Exit status of the command; None until the script records it.
        """
        path = self._path / self.exit_status_filename
        if not path.exists():
            return None
        return int(path.read_text())

    def _require_receipt(self) -> SubmissionReceipt:
        receipt = self.receipt
        if receipt is not None:
            return receipt
        if self.is_unresolved:
            msg = f"Submission of job {self.key!r} began without a receipt; reconcile"
            raise SubmissionUnresolvedError(msg)
        msg = f"Job {self.key!r} has not been submitted"
        raise ValueError(msg)

    def _write_receipt(self, receipt: SubmissionReceipt) -> None:
        _write_atomic(
            self._path / self.receipt_filename, receipt.model_dump_yaml(mode="json")
        )
