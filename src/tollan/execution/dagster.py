"""Run supervised jobs from Dagster assets through Dagster Pipes.

Requires the ``dagster`` extra (``pip install tollan[dagster]``). The external
process uses ``dagster-pipes`` to receive its context and report results.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING, Any

import dagster as dg

from .job import JobRecord, SubmissionUnresolvedError
from .scheduler import get_scheduler
from .supervise import SupervisionOutcomeKind, cancel_job, supervise_job

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from dagster._core.pipes.context import PipesMessageHandler

    from .job import JobStatus, Scheduler, SubmissionReceipt
    from .policy import JobSpec

__all__ = ["PipesJobClient"]

#: Pipes context of the external process, kept in the job record.
PIPES_CONTEXT_FILENAME = "pipes_context.json"
#: Pipes messages of the external process, kept in the job record.
PIPES_MESSAGES_FILENAME = "pipes_messages.jsonl"


class _RecordContextInjector(dg.PipesContextInjector):
    """Keep the context of the first session in the job record."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.context_data: Mapping[str, Any] | None = None

    @contextmanager
    def inject_context(self, context_data: Any) -> Iterator[dict[str, str]]:
        # The record may not exist yet; the client writes the file once it does.
        self.context_data = context_data
        yield {"path": str(self.path)}

    def write_once(self) -> None:
        if self.path.exists():
            return
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_text(json.dumps(self.context_data))
        temporary.replace(self.path)

    def no_messages_debug_text(self) -> str:
        return f"Context for the external process is in {self.path}."


class _RecordMessageReader(dg.PipesMessageReader):
    """Read every message in the job record, including earlier sessions'."""

    def __init__(self, path: Path, final_message_timeout: float) -> None:
        self.path = path
        self.final_message_timeout = final_message_timeout

    @contextmanager
    def read_messages(self, handler: PipesMessageHandler) -> Iterator[dict[str, Any]]:
        stop = Event()
        thread = Thread(target=self._read, args=(handler, stop), daemon=True)
        thread.start()
        try:
            yield {"path": str(self.path), "include_stdio_in_messages": False}
        except BaseException:
            stop.set()
            thread.join()
            raise
        # Report results only after the external process closed its messages.
        thread.join(self.final_message_timeout)
        if thread.is_alive():
            stop.set()
            thread.join()
            msg = f"External process did not close its Pipes messages: {self.path}"
            raise dg.DagsterPipesExecutionError(msg)

    def _read(self, handler: PipesMessageHandler, stop: Event) -> None:
        position = 0
        try:
            while True:
                final = stop.is_set()
                if self.path.exists():
                    # Reopen between reads, so files on shared storage refresh.
                    with self.path.open(encoding="utf-8") as stream:
                        stream.seek(position)
                        while (line := stream.readline()).endswith("\n"):
                            handler.handle_message(json.loads(line))
                            position = stream.tell()
                            if handler.received_closed_message:
                                return
                if final:
                    return
                stop.wait(0.1)
        except Exception:  # noqa: BLE001 -- Reported to Dagster as Pipes does.
            handler.report_pipes_framework_exception(
                f"{type(self).__name__} reader thread", sys.exc_info()
            )

    def no_messages_debug_text(self) -> str:
        return f"Messages of the external process are in {self.path}."


class PipesJobClient(dg.ConfigurableResource, dg.PipesClient):
    """Run an external process as a supervised job from a Dagster asset.

    The job record keeps the Pipes context and messages, so a later run can
    reattach to the job and read every message. Interrupting the run leaves the
    job running, except when the run is canceled, which cancels the job.

    Attributes
    ----------
    poll_interval : float
        Seconds between job observations.
    unknown_grace : float
        Seconds the job's state may stay unknown before the run fails.
    cancel_timeout : float
        Seconds to confirm cancellation of a canceled run's job.
    final_message_timeout : float
        Seconds to wait, after the job succeeds, for the external process's
        remaining Pipes messages.
    """

    poll_interval: float = 5
    unknown_grace: float = 60
    cancel_timeout: float = 60
    final_message_timeout: float = 30

    # PipesClient.run lets clients add keyword arguments to context and extras.
    def run(  # noqa: PLR0913 # ty:ignore[invalid-method-override]
        self,
        *,
        context: dg.AssetExecutionContext | dg.OpExecutionContext,
        spec: JobSpec,
        key: str,
        command: Sequence[str],
        check: Callable[[JobRecord], bool] | None = None,
        extras: Mapping[str, Any] | None = None,
    ) -> dg.PipesClientCompletedInvocation:
        """Submit or reattach to a job and wait for its outcome.

        Parameters
        ----------
        context : dagster.AssetExecutionContext or dagster.OpExecutionContext
            Context of the current asset or op.
        spec : JobSpec
            Job spec of a new job; ignored when the record already exists.
        key : str
            Record key. An existing record with this key is reattached, not
            resubmitted; a retried computation needs a new key.
        command : sequence of str
            Program and arguments of the external process of a new job.
        check : callable or None
            Result check of the job record; see `supervise_job`. Default is None.
        extras : mapping or None
            Extra data passed to the external process. Default is None.

        Returns
        -------
        dagster.PipesClientCompletedInvocation
            Completed invocation holding the results the external process
            reported.

        Raises
        ------
        dagster.Failure
            The job did not succeed. Retries are not allowed when the job's
            submission or state is unresolved.
        """
        path = Path(str(spec.profile.job_records_path)) / key
        injector = _RecordContextInjector(path / PIPES_CONTEXT_FILENAME)
        reader = _RecordMessageReader(
            path / PIPES_MESSAGES_FILENAME, self.final_message_timeout
        )
        with dg.open_pipes_session(
            context=context,
            context_injector=injector,
            message_reader=reader,
            extras=extras,
        ) as session:
            if (path / JobRecord.job_filename).exists():
                record = JobRecord.open(path)
            else:
                env = session.get_bootstrap_env_vars()
                record = JobRecord.create(spec, key=key, command=command, env=env)
            injector.write_once()
            scheduler = get_scheduler(record.spec.profile)
            receipt = self._submit(record, scheduler)
            context.log.info(f"Job {record.key} ({receipt.native_id}) at {path}")
            session.report_launched(
                {"extras": {"job_record": str(path), "native_id": receipt.native_id}}
            )
            self._supervise(context, record, scheduler, check)
        return dg.PipesClientCompletedInvocation(session)

    @staticmethod
    def _submit(record: JobRecord, scheduler: Scheduler) -> SubmissionReceipt:
        try:
            if record.is_unresolved:
                receipt = record.reconcile(scheduler)
                if receipt is not None:
                    return receipt
            return record.submit(scheduler)
        except SubmissionUnresolvedError as error:
            raise dg.Failure(description=str(error), allow_retries=False) from error

    def _supervise(
        self,
        context: dg.AssetExecutionContext | dg.OpExecutionContext,
        record: JobRecord,
        scheduler: Scheduler,
        check: Callable[[JobRecord], bool] | None,
    ) -> None:
        def log(status: JobStatus) -> None:
            context.log.info(
                f"Job {record.key}: {status.state} ({status.native_state})"
            )

        try:
            outcome = supervise_job(
                record,
                scheduler,
                check=check,
                poll_interval=self.poll_interval,
                unknown_grace=self.unknown_grace,
                on_status=log,
            )
        except dg.DagsterExecutionInterruptedError:
            run = context.instance.get_run_by_id(context.run.run_id)
            if run is not None and run.status == dg.DagsterRunStatus.CANCELING:
                canceled = cancel_job(
                    record,
                    scheduler,
                    timeout=self.cancel_timeout,
                    poll_interval=self.poll_interval,
                )
                context.log.info(canceled.message)
            raise
        if outcome.kind != SupervisionOutcomeKind.succeeded:
            raise dg.Failure(
                description=outcome.message,
                allow_retries=outcome.kind != SupervisionOutcomeKind.unresolved,
            )
