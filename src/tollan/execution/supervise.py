"""Supervision: wait for a job's outcome and act on it."""

from __future__ import annotations

import time
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from tollan.config import FrozenBaseModel

from .job import JobState, JobStatus
from .transport import SchedulerCommandError, TransportError

if TYPE_CHECKING:
    from collections.abc import Callable

    from .job import JobRecord, Scheduler

__all__ = [
    "SupervisionOutcome",
    "SupervisionOutcomeKind",
    "cancel_job",
    "supervise_job",
]


class SupervisionOutcomeKind(StrEnum):
    """Categories of supervision outcomes."""

    #: Completed with exit status 0 and accepted by the result check.
    succeeded = auto()
    #: Finished unsuccessfully, or rejected by the result check.
    failed = auto()
    #: Finished by cancellation, or reached a terminal state after cancellation.
    canceled = auto()
    #: Cancellation was requested, but no terminal state was observed in time.
    cancel_requested = auto()
    #: The job's state stayed unknown beyond the grace period.
    unresolved = auto()


class SupervisionOutcome(FrozenBaseModel):
    """Outcome of supervising or canceling a job.

    Attributes
    ----------
    kind : SupervisionOutcomeKind
        Category of the outcome.
    status : JobStatus or None
        Last observed status; None when no status was observed.
    message : str
        Description of the outcome.
    """

    kind: SupervisionOutcomeKind
    status: JobStatus | None
    message: str


def _observe(record: JobRecord, scheduler: Scheduler) -> JobStatus | str:
    try:
        return record.status(scheduler)
    except (TransportError, SchedulerCommandError) as error:
        return str(error)


def _terminal_outcome(
    record: JobRecord,
    status: JobStatus,
    check: Callable[[JobRecord], bool] | None,
) -> SupervisionOutcome:
    kind = SupervisionOutcomeKind
    if status.state == JobState.canceled:
        return SupervisionOutcome(
            kind=kind.canceled, status=status, message=f"Job {record.key} canceled"
        )
    if status.state != JobState.completed or status.exit_code != 0:
        message = (
            f"Job {record.key} {status.state} with exit status {status.exit_code} "
            f"({status.native_state})"
        )
        return SupervisionOutcome(kind=kind.failed, status=status, message=message)
    if check is not None and not check(record):
        message = f"Job {record.key} completed, but its result check failed"
        return SupervisionOutcome(kind=kind.failed, status=status, message=message)
    return SupervisionOutcome(
        kind=kind.succeeded, status=status, message=f"Job {record.key} succeeded"
    )


def supervise_job(  # noqa: PLR0913 -- Supervision bounds are independent settings.
    record: JobRecord,
    scheduler: Scheduler,
    *,
    check: Callable[[JobRecord], bool] | None = None,
    poll_interval: float = 5,
    unknown_grace: float = 60,
    on_status: Callable[[JobStatus], None] | None = None,
) -> SupervisionOutcome:
    """Wait for a submitted job to finish and evaluate its outcome.

    Supervision observes the job until it reaches a terminal state; it never
    submits, resubmits or cancels the job. Stopping the supervising process,
    for example with KeyboardInterrupt, leaves the job running, so a new process
    can open the record and supervise it again.

    Parameters
    ----------
    record : JobRecord
        Submitted job record.
    scheduler : Scheduler
        Scheduler of the record's profile kind.
    check : callable or None
        Result check called with the record after the job completes with exit
        status 0; returning False fails the job. Default is None, which accepts
        every completed job.
    poll_interval : float
        Seconds between observations. Default is 5.
    unknown_grace : float
        Seconds the job's state may stay unknown, or unobservable because the
        scheduler cannot be reached, before supervision reports it unresolved.
        Default is 60.
    on_status : callable or None
        Called with each observed status that differs from the previous one.
        Default is None.

    Returns
    -------
    SupervisionOutcome
        ``succeeded``, ``failed`` or ``canceled`` for a terminal job;
        ``unresolved`` when its state stayed unknown beyond ``unknown_grace``.
        The record is retained in every case.
    """
    previous: JobStatus | None = None
    unknown_since: float | None = None
    while True:
        observed = _observe(record, scheduler)
        status = observed if isinstance(observed, JobStatus) else None
        if status is not None and (previous is None or not previous.same_as(status)):
            if on_status is not None:
                on_status(status)
            previous = status
        if status is not None and status.state.is_terminal:
            return _terminal_outcome(record, status, check)
        if status is None or status.state == JobState.unknown:
            unknown_since = unknown_since or time.monotonic()
            if time.monotonic() - unknown_since > unknown_grace:
                reason = observed if isinstance(observed, str) else "state unknown"
                return SupervisionOutcome(
                    kind=SupervisionOutcomeKind.unresolved,
                    status=previous,
                    message=f"Job {record.key} unresolved: {reason}",
                )
        else:
            unknown_since = None
        time.sleep(poll_interval)


def cancel_job(
    record: JobRecord,
    scheduler: Scheduler,
    *,
    timeout: float = 60,
    poll_interval: float = 5,
) -> SupervisionOutcome:
    """Cancel a job and confirm that it reaches a terminal state.

    Parameters
    ----------
    record : JobRecord
        Submitted job record.
    scheduler : Scheduler
        Scheduler of the record's profile kind.
    timeout : float
        Seconds to wait for a terminal state. Default is 60.
    poll_interval : float
        Seconds between observations. Default is 5.

    Returns
    -------
    SupervisionOutcome
        ``canceled`` once a terminal state is observed, with that status; the
        job may have finished on its own first. ``cancel_requested`` when no
        terminal state is observed within ``timeout``.
    """
    record.cancel(scheduler)
    deadline = time.monotonic() + timeout
    status: JobStatus | None = None
    while True:
        observed = _observe(record, scheduler)
        if isinstance(observed, JobStatus):
            status = observed
            if status.state.is_terminal:
                message = f"Job {record.key} {status.state} after cancellation"
                return SupervisionOutcome(
                    kind=SupervisionOutcomeKind.canceled, status=status, message=message
                )
        if time.monotonic() >= deadline:
            message = f"Cancellation of job {record.key} requested, not confirmed"
            return SupervisionOutcome(
                kind=SupervisionOutcomeKind.cancel_requested,
                status=status,
                message=message,
            )
        time.sleep(poll_interval)
