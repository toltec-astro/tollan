"""External execution: run computations through local or batch schedulers.

The placement policy decides where a workload runs and with which resources;
job records keep the durable state of each submitted job; supervision waits
for a job's outcome.
"""

from __future__ import annotations

from .job import (
    JobRecord,
    JobState,
    JobStatus,
    Scheduler,
    SubmissionReceipt,
    SubmissionUnresolvedError,
)
from .policy import (
    ExecutionPolicy,
    ExecutionPolicyConfig,
    ExecutionProfile,
    ExecutionProfileBase,
    ExecutionRequest,
    JobSpec,
    LocalProfile,
    ResourceLimits,
    ResourceRequest,
    Resources,
    SlurmProfile,
)
from .scheduler import LocalScheduler, SlurmScheduler, get_scheduler
from .supervise import (
    SupervisionOutcome,
    SupervisionOutcomeKind,
    cancel_job,
    supervise_job,
)
from .transport import (
    LocalTransport,
    SchedulerCommandError,
    SshTransport,
    Transport,
    TransportError,
)

__all__ = [
    "ExecutionPolicy",
    "ExecutionPolicyConfig",
    "ExecutionProfile",
    "ExecutionProfileBase",
    "ExecutionRequest",
    "JobRecord",
    "JobSpec",
    "JobState",
    "JobStatus",
    "LocalProfile",
    "LocalScheduler",
    "LocalTransport",
    "ResourceLimits",
    "ResourceRequest",
    "Resources",
    "Scheduler",
    "SchedulerCommandError",
    "SlurmProfile",
    "SlurmScheduler",
    "SshTransport",
    "SubmissionReceipt",
    "SubmissionUnresolvedError",
    "SupervisionOutcome",
    "SupervisionOutcomeKind",
    "Transport",
    "TransportError",
    "cancel_job",
    "get_scheduler",
    "supervise_job",
]
