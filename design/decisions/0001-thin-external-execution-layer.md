---
status: "accepted"
date: 2026-10-24
decision-makers: user [claude 2026-10-24]
---

# Build a thin execution layer instead of adopting a job library

## Context and Problem Statement

Applications run long computations as local processes or as Slurm jobs, with or
without Dagster. Slurm commands go through SSH to a submission host that is not
the deciding host. The deciding process can restart while a job runs, so a job
is submitted once only, and any process can find it again and reattach to it.
Should Tollan adopt an existing job library?

## Considered Options

* dagster-slurm
* PSI/J (ExaWorks)
* submitit
* Parsl
* A thin Tollan layer that borrows the vocabulary of PSI/J and Dagster

## Decision Outcome

Chosen option: "A thin Tollan layer that borrows the vocabulary of PSI/J and
Dagster", because no surveyed library supplies all of these together:
scheduler-neutral jobs, an SSH transport, a durable once-only job record,
reattachment, and an optional Dagster Pipes client.

| Option | What it does not supply |
| --- | --- |
| dagster-slurm | Use without Dagster. An earlier review of the Unity design also found no partition-safe recovery and no handling of an ambiguous submission or an unknown state. |
| PSI/J | An SSH transport (it runs scheduler commands on the local host) and a once-only submission record. |
| submitit | Command-line workers (it runs pickled Python callables), remote submission, and orchestration integration. |
| Parsl | Use beside Dagster: it is a second workflow system, with pilot jobs. |

Scheduler-facing terms follow PSI/J and Slurm (job spec, scheduler, native ID).
Orchestration-facing terms follow Dagster (Pipes, pools, forward termination).
Tollan does not use *executor*, *launcher* or a bare *attempt*, because Dagster
and Parsl already give these words other meanings.

Tollan ships no entry point or service. A caller-chosen record key and
reconciliation let any process find a job again.

### Consequences

* Good, because the core layers work without Dagster, and the Dagster
  integration is an optional extra.
* Good, because users of PSI/J and Dagster recognize the terms.
* Bad, because Tollan maintains its own local and Slurm schedulers. PSI/J
  remains a possible scheduler backend if more schedulers are needed.
