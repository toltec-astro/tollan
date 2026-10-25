"""External execution: run computations through local or batch schedulers.

The placement policy decides where a workload runs and with which resources.
"""

from __future__ import annotations

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
