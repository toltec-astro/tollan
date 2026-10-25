"""Placement policy: where workloads run and which resources they use.

A deployment declares execution profiles in the runtime's ``execution`` section.
An application states the workload and resources it needs as an
:class:`ExecutionRequest`; :class:`ExecutionPolicy` resolves it into a job spec
under the first profile that selects the workload::

    >>> from tollan.config import RuntimeContext
    >>> from tollan.execution import ExecutionPolicy, ExecutionRequest
    >>> rc = RuntimeContext()
    >>> rc.update_default_config(
    ...     {
    ...         "execution": {
    ...             "profiles": [
    ...                 {
    ...                     "kind": "local",
    ...                     "name": "laptop",
    ...                     "workloads": "reduce_.*",
    ...                     "job_records_path": "/tmp/jobs",
    ...                     "threads": 2,
    ...                 }
    ...             ],
    ...         }
    ...     }
    ... )
    >>> request = ExecutionRequest(workload="reduce_obs")
    >>> spec = ExecutionPolicy(rc).resolve(request)
    >>> spec.profile.name, spec.as_environ()["OMP_NUM_THREADS"]
    ('laptop', '2')
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal, Self, get_args

from astropy.units import Quantity
from pydantic import (
    AfterValidator,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from tollan.config import EnvConfig, FrozenBaseModel
from tollan.config.handler import ConfigHandler, SubConfigKeyTransformer
from tollan.config.types import (
    AbsAnyPath,
    HostPath,
    SafeName,
    StringSelector,
    TimeQuantityField,
    quantity_field,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ExecutionPolicy",
    "ExecutionPolicyConfig",
    "ExecutionProfile",
    "ExecutionProfileBase",
    "ExecutionRequest",
    "JobSpec",
    "LocalProfile",
    "ResourceLimits",
    "ResourceRequest",
    "Resources",
    "SlurmProfile",
]


def _check_positive(value: Quantity) -> Quantity:
    if value.value <= 0:
        msg = "Quantity must be positive"
        raise ValueError(msg)
    return value


_MEMORY_METADATA = get_args(quantity_field("data quantity"))[1:]
type MemoryQuantity = Annotated[
    Quantity, *_MEMORY_METADATA, AfterValidator(_check_positive)
]
"""A positive memory size, such as ``"16 GiB"``."""

type TimeLimitQuantity = Annotated[TimeQuantityField, AfterValidator(_check_positive)]
"""A positive walltime, such as ``"2 h"``."""

_THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


class ResourceLimits(FrozenBaseModel):
    """Maximum resources of one job.

    Attributes
    ----------
    cpus : int
        CPUs available to the job's single task.
    memory : astropy.units.Quantity
        Memory of the job, such as ``"16 GiB"``.
    time_limit : astropy.units.Quantity
        Walltime of the job, such as ``"2 h"``.
    """

    cpus: PositiveInt
    memory: MemoryQuantity
    time_limit: TimeLimitQuantity

    def exceeded_by(self, resources: ResourceLimits) -> list[str]:
        """Return the names of the limits that ``resources`` exceeds.

        Parameters
        ----------
        resources : ResourceLimits
            Requested resources.

        Returns
        -------
        list of str
            Exceeded limit names, in declaration order; empty when within limits.
        """
        return [
            name
            for name in ResourceLimits.model_fields
            if getattr(resources, name) > getattr(self, name)
        ]


class Resources(ResourceLimits):
    """Resources of one job: one task on one node.

    Attributes
    ----------
    cpus, memory, time_limit
        See `ResourceLimits`; here the values the job requests.
    threads : int or None
        Thread limit for numerical libraries in the external process; at most
        ``cpus``. None leaves threading to the external process. Default is None.
    """

    threads: PositiveInt | None = None

    @model_validator(mode="after")
    def _check_threads(self) -> Self:
        if self.threads is not None and self.threads > self.cpus:
            msg = "threads must not exceed cpus"
            raise ValueError(msg)
        return self


class ResourceRequest(FrozenBaseModel):
    """Resources requested for one job.

    Unset fields keep the profile's values. Local profiles accept only
    ``threads``.

    Attributes
    ----------
    cpus, threads : int or None
        See `Resources`.
    memory, time_limit : astropy.units.Quantity or None
        See `Resources`.
    """

    cpus: PositiveInt | None = None
    memory: MemoryQuantity | None = None
    time_limit: TimeLimitQuantity | None = None
    threads: PositiveInt | None = None


class ExecutionRequest(FrozenBaseModel):
    """Workload, resources and node selection an application requests for a job.

    Applications include it in their configuration to state how a computation
    runs externally; the deployment's execution profiles decide where.

    Attributes
    ----------
    workload : str
        Workload the job runs; selects the execution profile.
    resources : ResourceRequest
        Requested resources. Default requests none, keeping the profile's.
    nodes : StringSelector or None
        Node selection combined with the profile's; Slurm profiles only.
        Default is None.
    """

    workload: SafeName
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    nodes: StringSelector | None = None


class ExecutionProfileBase(FrozenBaseModel):
    """Fields shared by all execution profiles.

    Attributes
    ----------
    name : str
        Profile name.
    workloads : StringSelector
        Workloads the profile runs.
    env : EnvConfig
        Environment variables of the external process. Default is none.
    """

    name: SafeName
    workloads: StringSelector
    env: EnvConfig = Field(default_factory=lambda: EnvConfig({}))


class LocalProfile(ExecutionProfileBase):
    """Run selected workloads as processes on the orchestration host.

    Attributes
    ----------
    kind : "local"
        Profile kind.
    job_records_path : pathlib.Path
        Directory holding the job records. Relative paths use the validation
        context's ``root_path``.
    threads : int or None
        Thread limit for numerical libraries in the external process. Default
        is None, which leaves threading to the external process.
    """

    kind: Literal["local"]
    job_records_path: AbsAnyPath
    threads: PositiveInt | None = None

    def get_resources(self, request: ExecutionRequest) -> None:
        """Check a request; local jobs have no resources besides threads.

        Parameters
        ----------
        request : ExecutionRequest
            Request of the job.

        Raises
        ------
        ValueError
            The request sets resources other than ``threads``, or nodes.
        """
        unsupported = sorted(
            request.resources.model_dump(exclude_none=True).keys() - {"threads"}
        )
        if request.nodes is not None:
            unsupported.append("nodes")
        if unsupported:
            msg = f"Local profile {self.name!r} accepts only threads: {unsupported}"
            raise ValueError(msg)

    def get_threads(self, request: ExecutionRequest) -> int | None:
        """Return the thread limit of a job.

        Parameters
        ----------
        request : ExecutionRequest
            Request of the job.

        Returns
        -------
        int or None
            The requested thread limit, else the profile's.
        """
        threads = request.resources.threads
        return self.threads if threads is None else threads


class SlurmProfile(ExecutionProfileBase):
    """Run selected workloads through a Slurm partition within fixed limits.

    Attributes
    ----------
    kind : "slurm"
        Profile kind.
    job_records_path : HostPath
        Directory holding the job records; visible at the same path to the
        orchestration host, the submission host and the nodes.
    host : str or None
        Submission host reached over SSH, as named in the SSH configuration.
        None submits on the orchestration host. Default is None.
    partition : str
        Partition of every job.
    account : str or None
        Account charged for every job, if the site requires one.
    qos : str or None
        Quality of service of every job, if the site requires one.
    nodes : StringSelector
        Nodes of the partition that jobs may use. Default selects all.
    resources_default : Resources
        Resources of a job that requests none.
    resources_max : ResourceLimits
        Maximum resources of one job, including requested ones.
    """

    kind: Literal["slurm"]
    job_records_path: HostPath
    host: SafeName | None = None
    partition: SafeName
    account: SafeName | None = None
    qos: SafeName | None = None
    nodes: StringSelector = Field(
        default_factory=lambda: StringSelector.model_validate({"excludes": []})
    )
    resources_default: Resources
    resources_max: ResourceLimits

    @model_validator(mode="after")
    def _check_defaults(self) -> Self:
        exceeded = self.resources_max.exceeded_by(self.resources_default)
        if exceeded:
            msg = f"resources_default exceeds resources_max: {exceeded}"
            raise ValueError(msg)
        return self

    def get_resources(self, request: ExecutionRequest) -> Resources:
        """Return the resources of a job.

        Parameters
        ----------
        request : ExecutionRequest
            Request of the job.

        Returns
        -------
        Resources
            ``resources_default`` with the requested values applied.

        Raises
        ------
        ValueError
            The resources exceed ``resources_max`` or ``threads`` exceeds
            ``cpus``.
        """
        resources = Resources.model_validate(
            self.resources_default.model_dump()
            | request.resources.model_dump(exclude_none=True)
        )
        exceeded = self.resources_max.exceeded_by(resources)
        if exceeded:
            msg = f"Resources exceed the maximum of profile {self.name!r}: {exceeded}"
            raise ValueError(msg)
        return resources

    def get_threads(self, request: ExecutionRequest) -> int | None:
        """Return the thread limit of a job.

        Parameters
        ----------
        request : ExecutionRequest
            Request of the job.

        Returns
        -------
        int or None
            ``threads`` of the job's resources.
        """
        return self.get_resources(request).threads

    def select_nodes(
        self, request: ExecutionRequest, nodes: Iterable[str]
    ) -> list[str]:
        """Return the nodes a job may use.

        Parameters
        ----------
        request : ExecutionRequest
            Request of the job.
        nodes : iterable of str
            Nodes of the partition.

        Returns
        -------
        list of str
            Nodes selected by both the profile and the request, in input order.
        """
        selected = self.nodes.select(nodes)
        return selected if request.nodes is None else request.nodes.select(selected)


type ExecutionProfile = Annotated[
    LocalProfile | SlurmProfile, Field(discriminator="kind")
]
"""A local or Slurm execution profile, selected by its ``kind``."""


class JobSpec(FrozenBaseModel):
    """Request of one job and the profile that runs it.

    A job keeps the spec it was resolved with; reattachment and recovery reuse
    it instead of resolving the current policy again.

    Attributes
    ----------
    request : ExecutionRequest
        Workload, resources and node selection requested for the job.
    profile : LocalProfile or SlurmProfile
        Profile that runs the job, as configured when resolved.
    """

    request: ExecutionRequest
    profile: ExecutionProfile

    @property
    def resources(self) -> Resources | None:
        """Resources of the job; None for a local profile."""
        return self.profile.get_resources(self.request)

    def as_environ(self) -> dict[str, str]:
        """Return a fresh environment dict for the external process.

        The profile's environment with the job's thread limits, which take
        precedence. Merge with ``os.environ`` explicitly when starting the
        process; the merge order determines which values take precedence.
        """
        threads = self.profile.get_threads(self.request)
        env = self.profile.env.root.copy()
        if threads is not None:
            env.update(dict.fromkeys(_THREAD_VARIABLES, str(threads)))
        return env


class ExecutionPolicyConfig(FrozenBaseModel):
    """Execution profiles of a deployment.

    Attributes
    ----------
    profiles : list of LocalProfile or SlurmProfile
        Profiles with unique names, in selection order.
    """

    profiles: Annotated[list[ExecutionProfile], Field(min_length=1)]

    @field_validator("profiles")
    @classmethod
    def _check_unique_names(
        cls, profiles: list[ExecutionProfile]
    ) -> list[ExecutionProfile]:
        if len({profile.name for profile in profiles}) != len(profiles):
            msg = "Profile names must be unique"
            raise ValueError(msg)
        return profiles


class ExecutionPolicy(
    SubConfigKeyTransformer[Literal["execution"]],
    ConfigHandler[ExecutionPolicyConfig],
):
    """Resolve job specs from the runtime's ``execution`` section.

    Parameters
    ----------
    runtime_context : tollan.config.RuntimeContext
        Runtime holding the deployment's execution profiles.
    """

    def resolve(self, request: ExecutionRequest) -> JobSpec:
        """Resolve a request into a job spec under the first profile selecting it.

        Parameters
        ----------
        request : ExecutionRequest
            Workload, resources and node selection of the job.

        Returns
        -------
        JobSpec
            The request with the selected profile.

        Raises
        ------
        ValueError
            No profile selects the workload, the request sets values the
            profile's kind does not accept, or the resources exceed the
            profile's maximum.
        """
        profile = next(
            (p for p in self.config.profiles if p.workloads.matches(request.workload)),
            None,
        )
        if profile is None:
            msg = f"No execution profile selects workload {request.workload!r}"
            raise ValueError(msg)
        profile.get_resources(request)
        return JobSpec(request=request, profile=profile)
