# External execution

Run long computations outside the process that decides to run them: as a local
process while you develop, or on compute nodes through a batch scheduler such as
Slurm. Your deployment declares where workloads run and which resources they
may use; your application requests a workload and receives its job spec.

| Task | API |
| --- | --- |
| Declare where workloads run | execution profiles in the `execution` configuration section |
| State what a computation needs | `ExecutionRequest` in your configuration |
| Turn a request into a job spec | `ExecutionPolicy.resolve(request)` |
| Keep a job's settings with the job | `JobSpec.model_dump_yaml()`, `JobSpec.model_validate_yaml()` |

## Declare execution profiles

An **execution profile** says where the workloads it selects run, and with
which limits. A local profile runs jobs as processes on the local host. A Slurm profile fixes the submission host, partition, account and
quality of service, the nodes jobs may use, the resources of a job that
requests none (`resources_default`), and the largest job it accepts
(`resources_max`). Each profile names the directory of its job records, and its
`env` mapping holds environment variables for its external processes. Values
convert with Python's `str`, as for [dotenv values](configuration.md#use-dotenv-values).

Keep these settings with your deployment, for example in a YAML file loaded into
the runtime:

```{testcode}
from tollan.config import RuntimeContext
from tollan.execution import ExecutionPolicy
from tollan.utils.yaml import yaml_loads

site = """
execution:
  profiles:
  - kind: slurm
    name: cluster
    workloads: {includes: [reduce_obs, make_map]}
    job_records_path: /shared/jobs
    host: login.example.org
    partition: cpu
    account: group
    nodes: {excludes: [cpu3]}
    resources_default: {cpus: 4, memory: 8 GiB, time_limit: 1 h, threads: 2}
    resources_max: {cpus: 16, memory: 64 GiB, time_limit: 2 d}
    env: {PYTHONUNBUFFERED: 1}
  - kind: local
    name: laptop
    workloads: .*
    job_records_path: /data/jobs
"""

rc = RuntimeContext()
rc.update_default_config(yaml_loads(site))
policy = ExecutionPolicy(rc)
print([profile.name for profile in policy.config.profiles])
```

```{testoutput}
['cluster', 'laptop']
```

`workloads` and `nodes` are string selectors: a list of names, a regular
expression, or a mapping with `includes`, `excludes` or `pattern` (see
{doc}`validation-types`). A Slurm profile without `nodes` may use every node of
its partition.

Memory and walltime accept units, such as `8 GiB` and `90 min`. A local
`job_records_path` resolves like other local paths, including against the
validation context's `root_path`. A Slurm `job_records_path` must be an absolute
path visible at the same location on the local host, the submission host and the
compute nodes; it is used as written, without resolving it locally. Validation rejects
duplicate profile names and `resources_default` larger than `resources_max`.

## Request execution for a computation

An **execution request** states what your computation needs: the workload name,
the resources it requests, and optionally the nodes it may use. Include it in
your own configuration model, beside the settings of the computation, so a
deployment or a user can change the request without changing code:

```{testcode}
from tollan.config import FrozenBaseModel
from tollan.execution import ExecutionRequest

class MakeMapConfig(FrozenBaseModel):
    pixel_size: float = 1.0
    execution: ExecutionRequest = ExecutionRequest(workload="make_map")

config = MakeMapConfig()
print(config.execution.workload, config.execution.resources.cpus)
```

```{testoutput}
make_map None
```

Unset resources keep the selected profile's `resources_default`.

## Resolve a job spec

Resolve a request to get its **job spec**: the request together with the
profile that runs it. The first profile, in declared order, whose `workloads`
selects the workload runs it, so a catch-all profile goes last. A job runs one
task on one node; its resources and environment follow from the job spec.
Resolution reads only configuration and never contacts a scheduler:

```{testcode}
spec = policy.resolve(config.execution)
print(spec.profile.name, spec.resources.cpus, spec.resources.memory)
print(spec.as_environ()["OMP_NUM_THREADS"])

local = policy.resolve(ExecutionRequest(workload="calibrate"))
print(local.profile.name, local.resources)
```

```{testoutput}
cluster 4 8.0 Gibyte
2
laptop None
```

Local jobs have no resources besides an optional thread limit.

`as_environ()` returns a fresh dict with the profile's `env` values. When
`threads` is set, it also sets `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and
`MKL_NUM_THREADS`, which take precedence; `threads` may not exceed `cpus`. When
it is unset, the external process chooses its own threading. Merge the result
with `os.environ` explicitly when you start a process:

```{testcode}
import os

env = {**os.environ, **spec.as_environ()}
assert env["PYTHONUNBUFFERED"] == "1"
```

### Request different resources for one job

Requested resources may not exceed the profile's `resources_max`. A requested
node selection is combined with the profile's, so it never adds nodes the
profile excludes. Local profiles accept only `threads`.

```{testcode}
request = ExecutionRequest.model_validate(
    {
        "workload": "reduce_obs",
        "resources": {"cpus": 8, "memory": "32 GiB"},
        "nodes": ["cpu2", "cpu3"],
    }
)
spec = policy.resolve(request)
print(spec.resources.cpus, spec.resources.memory)
print(spec.profile.select_nodes(spec.request, ["cpu1", "cpu2", "cpu3"]))

for workload in ("reduce_obs", "calibrate"):
    try:
        policy.resolve(
            ExecutionRequest(workload=workload, resources={"cpus": 32})
        )
    except ValueError:
        print("rejected:", workload)
```

```{testoutput}
8 32.0 Gibyte
['cpu2']
rejected: reduce_obs
rejected: calibrate
```

`SlurmProfile.select_nodes` applies both selections to a list of the
partition's nodes.

### Keep the job spec with the job

Store the job spec with the job, so later work on that job uses the settings it
was resolved with, even after the deployment's policy changes. The job spec
round-trips through YAML, including the kind of its profile:

```{testcode}
from tollan.execution import JobSpec

kept = spec.model_dump_yaml(mode="json")
assert JobSpec.model_validate_yaml(kept) == spec
```
