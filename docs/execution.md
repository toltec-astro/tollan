# External execution

Run long computations outside the process that decides to run them: as a local
process while you develop, or on compute nodes through a batch scheduler such as
Slurm. Your deployment declares where workloads run and which resources they
may use; your application requests a workload, receives its job spec, and runs
the job through a job record that any of your processes can follow.

| Task | API |
| --- | --- |
| Declare where workloads run | execution profiles in the `execution` configuration section |
| State what a computation needs | `ExecutionRequest` in your configuration |
| Turn a request into a job spec | `ExecutionPolicy.resolve(request)` |
| Keep a job's settings with the job | `JobSpec.model_dump_yaml()`, `JobSpec.model_validate_yaml()` |
| Run a job and wait for its outcome | `JobRecord.create()`, `JobRecord.submit()`, `supervise_job()` |
| Follow or cancel a job from another process | `JobRecord.open()`, `JobRecord.status()`, `cancel_job()` |
| Recover an unresolved submission | `JobRecord.reconcile()` |
| Run jobs from Dagster assets | `tollan.execution.dagster.PipesJobClient` |

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
    workloads: {includes: [transform, render]}
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

class RenderConfig(FrozenBaseModel):
    dpi: int = 150
    execution: ExecutionRequest = ExecutionRequest(workload="render")

config = RenderConfig()
print(config.execution.workload, config.execution.resources.cpus)
```

```{testoutput}
render None
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

local = policy.resolve(ExecutionRequest(workload="summarize"))
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
        "workload": "transform",
        "resources": {"cpus": 8, "memory": "32 GiB"},
        "nodes": ["cpu2", "cpu3"],
    }
)
spec = policy.resolve(request)
print(spec.resources.cpus, spec.resources.memory)
print(spec.profile.select_nodes(spec.request, ["cpu1", "cpu2", "cpu3"]))

for workload in ("transform", "summarize"):
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
rejected: transform
rejected: summarize
```

`SlurmProfile.select_nodes` applies both selections to a list of the
partition's nodes.

### Keep the job spec with the job

A job record stores the job spec with the job, so later work on that job uses the
settings it was resolved with, even after the deployment's policy changes. The
job spec round-trips through YAML, including the kind of its profile:

```{testcode}
from tollan.execution import JobSpec

kept = spec.model_dump_yaml(mode="json")
assert JobSpec.model_validate_yaml(kept) == spec
```

## Run a job

A **job record** is a directory named by a key beneath the profile's
`job_records_path`. It keeps the job spec, the command, the job script, the
submission receipt, the observed status history and the job's output, so any
process with access to it can follow the job. Create a record, submit it with
the scheduler for its profile, and supervise it until it finishes:

```{testcode}
import sys
import tempfile

from tollan.execution import JobRecord, get_scheduler, supervise_job

jobs_dir = tempfile.mkdtemp()
local_rc = RuntimeContext()
local_rc.update_default_config(
    {
        "execution": {
            "profiles": [
                {
                    "kind": "local",
                    "name": "laptop",
                    "workloads": ".*",
                    "job_records_path": jobs_dir,
                }
            ]
        }
    }
)
spec = ExecutionPolicy(local_rc).resolve(ExecutionRequest(workload="transform"))
record = JobRecord.create(
    spec, key="transform-1", command=[sys.executable, "-c", "print('transformed')"]
)
scheduler = get_scheduler(spec.profile)
record.submit(scheduler)
outcome = supervise_job(record, scheduler, poll_interval=0.1)
print(outcome.kind, outcome.status.exit_code)
print((record.path / "output.log").read_text().strip())
```

```{testoutput}
succeeded 0
transformed
```

The key names the record and must be a `SafeName`; a second record with the
same key raises `FileExistsError`. Submission is once-only: submitting again
returns the first receipt. A local job runs detached, so it continues when
your process exits.

`supervise_job()` polls the job's status and returns an outcome:

| `outcome.kind` | Meaning |
| --- | --- |
| `succeeded` | The job completed with exit status 0 and passed your `check`, if given. |
| `failed` | The job failed, completed with a nonzero exit status, or failed `check`. |
| `canceled` | The job was canceled. |
| `unresolved` | The job's state stayed unknown, or the scheduler unreachable, beyond `unknown_grace`. |

Supervision never submits or cancels a job. Pass `check` to inspect the job's
results before accepting it, and `on_status` to receive each status change.

### Follow a job from another process

Open the record from any process that can read it, for example after a
restart, and observe or supervise the job again:

```{testcode}
same = JobRecord.open(record.path)
print(same.receipt == record.receipt, same.status(scheduler).state)
print(same.history[-1].state)
```

```{testoutput}
True completed
completed
```

Stopping the process that supervises a job does not stop the job. To run the
same work again, create a record with a new key.

### Cancel a job

`cancel_job()` records the cancellation request, asks the scheduler to stop
the job and waits for a terminal state:

```{testcode}
from tollan.execution import cancel_job

waiting = JobRecord.create(
    spec,
    key="transform-2",
    command=[sys.executable, "-c", "import time; time.sleep(60)"],
)
waiting.submit(scheduler)
outcome = cancel_job(waiting, scheduler, timeout=30, poll_interval=0.1)
print(outcome.kind, outcome.status.state)
```

```{testoutput}
canceled canceled
```

If no terminal state appears within `timeout`, the outcome is
`cancel_requested`.

```{testcleanup}
import shutil

shutil.rmtree(jobs_dir)
```

### Recover an unresolved submission

If a process stops after it began submitting a job but before it recorded the
receipt, the record is unresolved: `record.is_unresolved` is True, and
`submit()` raises `SubmissionUnresolvedError` rather than risk a second job.
From a process that is not still submitting, call `reconcile()`:

```python
receipt = record.reconcile(scheduler)
if receipt is None:
    receipt = record.submit(scheduler)
```

`reconcile()` records the job the scheduler reports for the record, or confirms
that none was submitted so you can submit again.

## Run jobs on Slurm

For a Slurm profile, `get_scheduler()` runs the Slurm commands on `host`
through `ssh`, or on the local host when `host` is unset. `ssh` comes from
`PATH` and runs without prompting, so configure host aliases, users and keys in
your SSH configuration. The job records directory must be visible at the same
path on the local host, the submission host and the compute nodes.

```python
spec = policy.resolve(ExecutionRequest(workload="transform"))
record = JobRecord.create(spec, key="transform-1", command=["python", "-m", "mytool"])
scheduler = get_scheduler(spec.profile)
record.submit(scheduler)
outcome = supervise_job(record, scheduler)
```

Each job is one task on one node. Submission names the job after its key, runs
it in the record directory and writes its output to `output.log`; it uses the
profile's partition, account and quality of service, the job's resources, and
excludes the partition nodes that the node selections leave out. A rejected
submission leaves the record unresolved. Status comes from Slurm accounting, or
from the queue while accounting has no entry yet. `SshTransport` and
`LocalTransport` raise `TransportError` when a command cannot run and
`SchedulerCommandError` when it fails; neither is a job state.

### Try jobs on a local Slurm cluster

A Tollan checkout includes a small Slurm cluster in Docker for trying Slurm
profiles and running the live Slurm tests. It has a submission host reached over
SSH, Slurm accounting, two compute nodes `c1` and `c2` in partition `cpu`, and
account `group`. Every container mounts the shared directory
`/tmp/tollan-slurm` at the same path; set `TOLLAN_SLURM_SHARED` to use another.
With Docker running:

```bash
cd tests/execution/slurm_cluster
just up      # build and start the cluster, then wait for idle nodes
just test    # run tests/execution/test_slurm_live.py against it
just shell   # open a shell on the submission host
just down    # stop the cluster
```

`just up` writes an SSH configuration for host `tollan-slurm` to
`/tmp/tollan-slurm/ssh/config`. To reach the cluster from your own code, use a
profile with `host: tollan-slurm`, `partition: cpu`, `account: group` and a
`job_records_path` inside `/tmp/tollan-slurm`, and add that configuration to
your SSH configuration, for example with
`Include /tmp/tollan-slurm/ssh/config`. The live tests are skipped unless
`TOLLAN_SLURM_SHARED` is set.

## Run jobs from Dagster

Install the `dagster` extra (`pip install "tollan[dagster]"`) and add a
`PipesJobClient` resource. In an asset, resolve the job spec and run the job;
the client submits it, supervises it and returns the results that the external
process reports through [Dagster Pipes](https://docs.dagster.io/guides/build/external-pipelines):

```python
import dagster as dg

from tollan.execution import ExecutionRequest
from tollan.execution.dagster import PipesJobClient


@dg.asset(partitions_def=dg.DailyPartitionsDefinition("2026-01-01"), pool="cluster")
def table(context: dg.AssetExecutionContext, client: PipesJobClient):
    spec = policy.resolve(ExecutionRequest(workload="transform"))
    invocation = client.run(
        context=context,
        spec=spec,
        key=f"table-{context.partition_key}",
        command=["python", "-m", "mytool.transform", context.partition_key],
    )
    return invocation.get_materialize_result()


defs = dg.Definitions(assets=[table], resources={"client": PipesJobClient()})
```

The external process reports through `dagster-pipes`:

```python
from dagster_pipes import open_dagster_pipes

with open_dagster_pipes() as pipes:
    pipes.report_asset_materialization(metadata={"rows": 3})
```

- The job record keeps the Pipes context and messages. A run that finds an
  existing record for its key reattaches to that job instead of submitting
  again, and reads every message. Derive the key from the work, such as the
  asset and partition; use a new key to compute the work again.
- The run reports results only after the external process closes its messages.
- Canceling the run cancels the job. Other interruptions of the run leave the
  job running for a later run to reattach.
- A job that fails fails the step, and Dagster's retry policy decides about
  retries. A job whose submission or state is unresolved fails the step without
  retries.
- Use Dagster [concurrency pools](https://docs.dagster.io/guides/operate/managing-concurrency)
  to limit how many jobs runs submit at once; Slurm enforces the cluster's
  capacity across all users.
