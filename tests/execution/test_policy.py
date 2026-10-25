"""Placement policy bounds where workloads run and which resources they use."""

from pathlib import PurePosixPath

import astropy.units as u
import pytest
from pydantic import ValidationError

from tollan.config import FrozenBaseModel, RuntimeContext
from tollan.execution import (
    ExecutionPolicy,
    ExecutionPolicyConfig,
    ExecutionRequest,
    JobSpec,
    LocalProfile,
    ResourceRequest,
    SlurmProfile,
)

RESOURCES = {"cpus": 4, "memory": "8 GiB", "time_limit": "1 h", "threads": 2}
CLUSTER = {
    "kind": "slurm",
    "name": "cluster",
    "workloads": {"pattern": "transform|render"},
    "job_records_path": "/shared/jobs",
    "env": {"OMP_NUM_THREADS": 99, "SITE": "hpc"},
    "host": "login.example.org",
    "partition": "cpu",
    "account": "group",
    "nodes": {"excludes": ["cpu3"]},
    "resources_default": RESOURCES,
    "resources_max": {"cpus": 16, "memory": "64 GiB", "time_limit": "2 d"},
}
LAPTOP = {
    "kind": "local",
    "name": "laptop",
    "workloads": {"pattern": ".*"},
    "job_records_path": "/data/jobs",
}
SITE = {"profiles": [CLUSTER, LAPTOP]}
PARTITION_NODES = ["cpu1", "cpu2", "cpu3"]


def slurm_resources(spec):
    assert isinstance(spec.profile, SlurmProfile)
    resources = spec.resources
    assert resources is not None
    return resources


def make_policy(*settings):
    rc = RuntimeContext()
    rc.update_default_config({"execution": SITE})
    for setting in settings:
        rc.update_override_config({"execution": setting})
    return ExecutionPolicy(rc)


def request(workload, *, nodes=None, **resources):
    values = {"workload": workload, "resources": resources}
    if nodes is not None:
        values["nodes"] = nodes
    return ExecutionRequest.model_validate(values)


# Profiles


@pytest.mark.parametrize(
    ("resources_max", "field"),
    [
        ({"cpus": 0, "memory": "64 GiB", "time_limit": "2 d"}, "cpus"),
        ({"cpus": 16, "memory": "0 GiB", "time_limit": "2 d"}, "memory"),
        ({"cpus": 16, "memory": "64 s", "time_limit": "2 d"}, "memory"),
        ({"cpus": 16, "memory": "64 GiB", "time_limit": "-1 h"}, "time_limit"),
        ({"cpus": 16, "memory": "64 GiB", "time_limit": "2 GiB"}, "time_limit"),
    ],
)
def test_limits_require_positive_values_of_the_right_kind(resources_max, field):
    with pytest.raises(ValidationError) as error:
        SlurmProfile.model_validate(CLUSTER | {"resources_max": resources_max})
    assert {e["loc"][-1] for e in error.value.errors()} == {field}


def test_slurm_profile_defaults_must_fit_its_maximum():
    resources = {"cpus": 32, "memory": "8 GiB", "time_limit": "1 h"}
    with pytest.raises(ValidationError, match=r"exceeds resources_max: \['cpus'\]"):
        SlurmProfile.model_validate(CLUSTER | {"resources_default": resources})


def test_slurm_profile_selects_all_partition_nodes_by_default():
    profile = SlurmProfile.model_validate(
        {k: v for k, v in CLUSTER.items() if k != "nodes"}
    )
    assert profile.nodes.select(PARTITION_NODES) == PARTITION_NODES


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"job_records_path": "relative/jobs"}, "job_records_path"),
        ({"host": "user@login"}, "host"),
        ({"partition": "-p"}, "partition"),
    ],
)
def test_slurm_profile_rejects_unsafe_values(changes, field):
    with pytest.raises(ValidationError) as error:
        SlurmProfile.model_validate(CLUSTER | changes)
    assert {e["loc"][0] for e in error.value.errors()} == {field}


def test_profile_names_must_be_unique():
    with pytest.raises(ValidationError, match="Profile names must be unique"):
        ExecutionPolicyConfig.model_validate({"profiles": [LAPTOP, LAPTOP]})


def test_local_records_path_resolves_against_the_root_path(tmp_path):
    rc = RuntimeContext().with_config(
        defaults={"execution": {"profiles": [LAPTOP | {"job_records_path": "jobs"}]}},
        validation_context={"root_path": tmp_path},
    )
    profile = ExecutionPolicy(rc).config.profiles[0]
    assert profile.job_records_path == (tmp_path / "jobs").resolve()


def test_policy_composes_through_configuration_sources():
    policy = make_policy({"profiles": [LAPTOP]})
    assert isinstance(policy.resolve(request("transform")).profile, LocalProfile)


# Workload selection


def test_first_profile_selecting_the_workload_runs_it():
    policy = make_policy()
    assert policy.resolve(request("render")).profile.name == "cluster"
    assert policy.resolve(request("summarize")).profile.name == "laptop"
    reordered = make_policy({"profiles": [LAPTOP, CLUSTER]})
    assert reordered.resolve(request("render")).profile.name == "laptop"


def test_workloads_no_profile_selects_are_rejected():
    policy = make_policy({"profiles": [CLUSTER]})
    with pytest.raises(ValueError, match="No execution profile selects workload"):
        policy.resolve(request("summarize"))


# Slurm resolution


def test_slurm_resolution_applies_profile_defaults():
    spec = make_policy().resolve(request("render"))
    assert spec.request == request("render")
    assert spec.profile.job_records_path == PurePosixPath("/shared/jobs")
    resources = slurm_resources(spec)
    assert resources.cpus == 4
    assert resources.memory == 8 * u.GiB
    assert resources.time_limit == 1 * u.h
    assert spec.profile.select_nodes(spec.request, PARTITION_NODES) == ["cpu1", "cpu2"]


def test_requested_resources_replace_defaults_within_the_maximum():
    spec = make_policy().resolve(
        request("transform", cpus=8, memory="32 GiB", time_limit="2 d")
    )
    resources = slurm_resources(spec)
    assert resources.cpus == 8
    assert resources.memory == 32 * u.GiB
    assert resources.time_limit == 2 * u.d
    assert resources.threads == 2


@pytest.mark.parametrize(
    ("requested", "match"),
    [
        ({"cpus": 32}, r"maximum of profile 'cluster': \['cpus'\]"),
        ({"memory": "128 GiB"}, r"\['memory'\]"),
        ({"time_limit": "3 d"}, r"\['time_limit'\]"),
        ({"cpus": 2, "threads": 4}, "threads must not exceed cpus"),
    ],
)
def test_requests_never_exceed_the_profile(requested, match):
    with pytest.raises(ValueError, match=match):
        make_policy().resolve(request("transform", **requested))


@pytest.mark.parametrize(
    ("requested", "selected"),
    [
        (["cpu2"], ["cpu2"]),
        ({"pattern": "cpu[23]"}, ["cpu2"]),
        (["cpu3"], []),
        (["cpu9"], []),
    ],
)
def test_requested_nodes_only_narrow_the_profile_selection(requested, selected):
    spec = make_policy().resolve(request("transform", nodes=requested))
    assert isinstance(spec.profile, SlurmProfile)
    assert spec.profile.select_nodes(spec.request, PARTITION_NODES) == selected


def test_thread_limits_take_precedence_over_the_profile_environment():
    spec = make_policy().resolve(request("transform", threads=3))
    assert spec.as_environ()["SITE"] == "hpc"
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert spec.as_environ()[name] == "3"


def test_unset_threads_leave_threading_to_the_external_process():
    resources = RESOURCES | {"threads": None}
    policy = make_policy({"profiles": [CLUSTER | {"resources_default": resources}]})
    spec = policy.resolve(request("transform"))
    assert slurm_resources(spec).threads is None
    assert spec.as_environ() == {"OMP_NUM_THREADS": "99", "SITE": "hpc"}


# Local resolution


def test_local_jobs_set_threads_only_when_given():
    policy = make_policy()
    assert policy.resolve(request("summarize")).as_environ() == {}
    spec = policy.resolve(request("summarize", threads=4))
    assert spec.resources is None
    assert spec.as_environ()["OMP_NUM_THREADS"] == "4"


@pytest.mark.parametrize(
    "requested", [{"cpus": 2}, {"memory": "1 GiB"}, {"nodes": ["cpu1"]}]
)
def test_local_profiles_accept_only_thread_requests(requested):
    with pytest.raises(ValueError, match="accepts only threads"):
        make_policy().resolve(request("summarize", **requested))


def test_resolution_contacts_no_scheduler(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError

    monkeypatch.setattr("subprocess.run", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    make_policy().resolve(request("transform"))


# Job spec retention


@pytest.mark.parametrize(
    ("workload", "kind"), [("transform", SlurmProfile), ("summarize", LocalProfile)]
)
def test_job_specs_round_trip_through_yaml(workload, kind):
    spec = make_policy().resolve(request(workload, threads=1))
    restored = JobSpec.model_validate_yaml(spec.model_dump_yaml(mode="json"))
    assert type(restored.profile) is kind
    assert restored == spec


def test_a_kept_job_spec_ignores_later_policy_changes():
    kept = make_policy().resolve(request("transform")).model_dump_yaml(mode="json")
    narrowed = make_policy(
        {
            "profiles": [
                CLUSTER
                | {
                    "resources_default": {
                        "cpus": 1,
                        "memory": "1 GiB",
                        "time_limit": "1 h",
                    },
                    "resources_max": {
                        "cpus": 2,
                        "memory": "4 GiB",
                        "time_limit": "1 h",
                    },
                }
            ]
        }
    )
    assert slurm_resources(narrowed.resolve(request("transform"))).cpus == 1
    assert slurm_resources(JobSpec.model_validate_yaml(kept)).cpus == 4


def test_applications_embed_the_request_in_their_configuration():
    class RenderConfig(FrozenBaseModel):
        dpi: int = 150
        execution: ExecutionRequest = ExecutionRequest(workload="render")

    config = RenderConfig.model_validate(
        {"execution": {"workload": "render", "resources": {"cpus": 8}}}
    )
    spec = make_policy().resolve(config.execution)
    assert slurm_resources(spec).cpus == 8
    assert RenderConfig().execution.resources == ResourceRequest()
