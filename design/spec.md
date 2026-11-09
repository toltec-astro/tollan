# Tollan specification

## Overview

### Purpose and scope

Tollan provides reusable infrastructure for scientific Python applications.
Applications define domain semantics and operational policy. Tollan provides
interfaces that separate those decisions from reusable operations.

### Concepts and responsibilities

- Each domain defines its own contracts and the handoffs needed for its workflows.
- Data access and application configuration are independent entry paths. Analyses
  and execution combine them; callers may use each domain independently.
- Configuration, execution state, and scientific results are distinct objects
  with distinct lifetimes.

Analyses and steps separate complete workflows from reusable computations:

| API level | Responsibility |
| --- | --- |
| High | Prepare and execute a complete configured operation, including its result or invocation lifecycle. |
| Middle | Adapt domain inputs, apply settings, combine computations, and assemble results through the domain's data interchange contract. |
| Low | Compute from numerical inputs and explicit parameters, independently of configuration models, views, mappers, output namespaces, and invocation contexts. |

- Low-level computations preserve inputs and do not consult mutable class state.
- Concrete components define their input and result contracts. They may delegate
  computation to existing analyses or utilities; the levels do not require
  duplicate APIs or an otherwise unnecessary method.

## Domains

### Data access and representation

Data writers commonly produce batches of files with a shared layout and different
values. The schema/mapper/view system provides semantic access across such batches
without repeating storage-specific lookups in consumer code. Resolving a mapper
prepares reusable bindings for that layout; reuse across compatible sources is
an intended mode of operation, not an exception.

#### Schemas and mappings

- Schemas and mappings provide reusable semantic access across batches of
  compatible data sources.
- A schema assigns semantic names to entities that may occur in a data source.
- A mapping defines how to resolve one entity. Its binding records the entity
  kind and location.
- Attributes, variables, dimensions, and subtrees remain distinct when their
  names coincide.
- A mapper resolves mappings against a source and records the resulting bindings.
  Read operations apply those bindings to the supplied source.
- Resolution does not materialize array values unless a mapping explicitly
  requests value resolution.
- Reuse a resolved mapper across sources with the same layout or compatible
  subsets and extensions. Complete source layouts need not be identical.
- Compatibility is specific to the requested operation: the source must supply
  the bindings that operation requires. Additional fields and omitted unused
  fields do not prevent reuse.
- Reusing layout bindings preserves each source's values and identity; it does
  not substitute values from another source in the batch.

#### Accessors and views

- A schema-bound accessor combines a source and mapper into a domain API.
- An accessor or view treats its bound source as read-only. It does not own
  modifications to that source.
- A view accesses the bound source and content below it. It does not search
  parents or siblings for data.
- A view may expose a descendant of its source through a subview.
- A view assumes that its bound source remains valid for its lifetime. It does
  not detect source changes, refresh cached state, or rebind itself. The component
  that changes the source is responsible for managing affected view lifetimes.
- The concrete accessor defines compatibility validation and the operations that
  require additional validation.
- A resolved mapper, and an accessor or view built on it, can be pickled with its
  source, so that [invocation contexts](#context-identity-and-serialization)
  that reference data through views can be transported. Restoring uses the
  recorded bindings and does not resolve the mappings against the source again.

#### Lazy data and resource ownership

- Lazy access lets callers select data and defer computation without loading the
  entire source. Resource ownership defines who keeps that work executable.
- Tollan does not trigger computation or fetch all source data when the requested
  operation does not require it.
- Wrapping a borrowed source or engine does not transfer responsibility for its
  resources to Tollan.

#### Backend adapters

- Backend adapters expose schema-based access through each container's native
  data model.
- An adapter implements entity resolution and access for its backend.
- Hierarchical access uses an explicitly selected source scope. View boundaries
  follow [accessors and views](#accessors-and-views).
- Container conversion preserves the selected data's meaning. Its contract states
  whether the result is independently editable and whether conversion requires
  evaluating deferred data.

#### Units and table conversion

- Unit and table adapters let scientific consumers use Astropy quantities and
  quantity-aware tables with data stored in other containers.
- Their scope is the conversion between numeric arrays with unit metadata and
  Astropy representations; source containers need not store Astropy objects.
- Quantity access interprets the source's unit metadata and presents values with
  their physical units. Unit attachment presents a view of the existing data
  wherever its representation permits, without unnecessary copying or evaluation.
- Table projection presents selected data as an Astropy quantity-aware table,
  preserving row correspondence, values, and units.
- Conversion performs the data access needed to construct the Astropy
  representation. Read-only use does not require an independent copy.
- Callers that need in-place table edits can obtain independently owned data.
  Edits to that table must not alter the source; establishing this independence
  may require copying all selected data.

#### Model tables

- Model tables collect selected object attributes into a mutable, flat table
  for filtering and incremental enrichment. They need no shared model class and
  never serialize or reconstruct the input objects.
- Applications declare attribute paths, output representations and query
  vocabulary. Projection reads only the declared attributes and preserves input
  row order. Declarations generated from annotations read no object values and
  are reusable across batches; reads stay duck-typed.
- Each object uses exactly one projection. Projections of different object types
  may fill one column; all projections that write a column agree on its type,
  and a conflict fails before any value is read.
- Column storage never changes converted values: no truncation, overflow,
  precision loss, or null replaced by a value. Converters own intentional
  changes.
- Enrichment updates explicitly addressed rows and keeps the columns a
  projection omits. Changes are not synchronized back to the objects. Copying
  and in-place enrichment are explicit choices; in-place assignment is not
  transactional.
- Ordered record rules classify each record, from mapping keys or object
  attributes, into one result: the first matching rule wins, and unmatched
  records get the default, which a call may override without changing the
  rules. Batch evaluation over table columns gives the same results as record
  evaluation and modifies no input. A missing field never matches.

#### Read and inspect scientific data

- **Handoff:** opened or borrowed source → mapper → accessor → requested values.
- The application chooses the source and concrete reader. Validation follows
  [accessors and views](#accessors-and-views).
- Borrowed and owned resources follow
  [lazy data and resource ownership](#lazy-data-and-resource-ownership).


### Application configuration

Scientific applications run the same operations with different input-dependent,
site, and invocation settings. The configuration system supports modular settings
and composition from multiple locations and formats. It provides consistent,
convenient entry points for defaults and overrides. Validation gives each
component typed settings before it uses them.

#### Runtime context and component settings

- Runtime configuration supports applying shared settings to input-dependent
  component instances.
- A runtime context maintains the application's configuration sources, overrides,
  and evaluation context.
- A configured component captures validated settings from the runtime.
- User-configuration models use strict type validation, are frozen by default,
  and validate declared defaults and default-factory results. Different validation
  or mutation protocols require explicit exceptions.
- Validated settings support YAML persistence.
- Callers can inspect declared defaults without instantiating a configured
  component or executing code that generates a default value.
- The application supplies evaluation context before constructing components
  whose settings depend on it.
- Subsequent runtime changes do not alter an existing component's settings.
  Recreating the component captures settings from the updated runtime.

#### Configuration sources and precedence

- Configuration sources compose modular settings from different locations and
  formats through a common loading interface.
- A dictionary without `data` supplies in-memory settings as one source. A
  dictionary with `data` declares a source collection and must contain a valid
  source list. Invalid collections do not fall back to settings. Settings that
  contain `data` can be supplied through an explicit dictionary source.
- Source composition defines the order in which settings override earlier values.
  Each source list has independent ordering; a nested list contributes at its
  enclosing source's position.
- Relative file references resolve against a supplied base directory or the
  working directory; references inside a YAML source list resolve against that
  file's directory. Validation opens no referenced file and does not rewrite
  paths inside settings.
- Evaluation context supplies values used to select or evaluate settings.
- Evaluating settings for another input, including through a runtime variant,
  reuses the sources' earlier reads. Only an explicit refresh reads external
  sources again.
- Environment values come from dotenv files and from the `_env` section of the
  configuration. They are validated as strings and returned as a new mapping,
  which the caller merges with the process environment; reading them never
  changes the process environment.

#### Scientific value types

- Scientific field types make physical values and resource locations usable in
  validated configuration and metadata models.
- A field serializer produces the representation used to restore the validated
  value. The representation need not preserve the original input syntax.
- Relative descendant paths follow one lexical contract in configuration fields
  and subtree mappings: POSIX syntax, with redundant separators and
  current-directory components removed; rooted paths and parent traversal are
  rejected. The root itself is accepted only where a declaration also searches
  the containing directory. Validation needs no existing root, accesses no
  filesystem and does not check symlink containment.
- A string selector chooses names by exact inclusion, exact exclusion or a
  regular expression that must match the whole name. A plain string is a
  pattern and a list is an inclusion list. An empty inclusion list selects
  nothing; an empty exclusion list selects everything. Selection normalizes no
  string.
- A safe name is a restricted identifier usable in file names, scheduler job
  names and record keys. A safe name path joins safe names with `/` and may
  start with one `qualifier:` prefix. A host path names an absolute path on a
  given host.
- Time serialization preserves precision independently of display settings.

### Command-line applications

Applications need consistent command-line entry points without repeating common
CLI setup. Tollan provides a specialized Typer class for this purpose, so each
application can concentrate on its commands and their behavior.

- Shared setup provides version reporting, group help, and logging conventions.
- Generated command and option names preserve underscores. Multi-value options
  accept values after one flag and accumulate values across repeated flags.

#### Configuration integration

- Configuration integration gives command-line applications access to the shared
  runtime configuration system.
- It translates selected arguments into inputs to
  [configuration sources and precedence](#configuration-sources-and-precedence).

#### Configure and launch an application

- **Handoff:** application arguments and selected sources → runtime → configured
  component → application callback.
- CLI arguments enter the runtime through
  [configuration integration](#configuration-integration). Evaluation context
  follows [runtime context and component settings](#runtime-context-and-component-settings).


### Analyses and results

Scientific users apply configured calculations to selected data, compare results,
and inspect computed outputs. Analyses associate results
with the settings that produced them. Result access is independent of the
application that scheduled the calculation.

#### Computation and producing configuration

- Producing configuration associates a scientific result with the settings used
  to calculate it.
- An analysis owns its validated configuration and computation, and manages
  its output scope.
- Installed results retain the configuration used to produce them. Later changes
  to application settings do not change that recorded configuration.
- When a step invokes the analysis, the step records its execution separately
  from the analysis's producing configuration.
- Deferred execution follows
  [lazy data and resource ownership](#lazy-data-and-resource-ownership).

#### Reusable analysis computations

- Reusable computations let callers calculate with the same analysis settings
  without preparing an output namespace or running the complete workflow.
- At the middle [API level](#concepts-and-responsibilities), an analysis also
  integrates results: the shared analysis base validates, reuses, and installs
  them with their producing configuration. A focused computation can instead
  return a standalone result.

#### Result views

- A result view resolves analysis outputs and their producing configuration.
- A result view accepts a reopened result namespace whose layout and producing
  configuration metadata satisfy the analysis contract. It reconstructs the
  concrete analysis and its recorded settings without the original analysis
  instance, pipeline invocation, or recomputation.
- This input contract covers interpretation of restored result metadata. It does
  not require Tollan to save results or guarantee storage-backend round trips.
- View lifetime follows [accessors and views](#accessors-and-views).

#### Inputs and output scopes

- Input selection and output scopes let analyses operate within a larger data
  hierarchy without taking ownership of unrelated data.
- An analysis receives selected inputs and a shared output scope. Multiple
  analyses may use the same scope, each owning a distinct result namespace.
- Shared scopes may retain scalar data variables. Scope nodes must have no local
  or inherited dimensions or coordinates.
- The analysis identifies the outputs it owns. Outputs can use independent
  coordinate systems without constraining one another.
- Output installation preserves data outside the owned locations.

#### Result reuse and replacement

- Result reuse avoids repeating a calculation when an existing result satisfies
  the requested analysis. Replacement updates results within the analysis scope.
- The concrete analysis defines the conditions for reusing an existing result.
  Configuration equality alone does not establish input equivalence.
- An analysis composes its complete result namespace before installation.
  Successful installation replaces that namespace as a unit, including any
  partial or previous contents. Failed composition leaves installed results
  unchanged. Other namespaces in the shared scope remain unchanged.

#### Compute and inspect analysis results

- **Handoff:** selected input view and settings → analysis output scope → result view.
- The caller selects inputs and an output scope as defined under
  [inputs and output scopes](#inputs-and-output-scopes). Step invocation follows
  [computation and producing configuration](#computation-and-producing-configuration).


### Steps and pipelines

Processing applications combine steps whose input and output requirements form
a dependency graph. Steps expose operations and invocation records; an execution
driver determines their scheduling. A sequential pipeline is one driver: it uses
an application-supplied order to accommodate those dependencies. Step contracts
are independent of this strategy and permit other drivers, including scheduling
by a directed acyclic graph (DAG).

#### Steps and configuration

- A step invokes an operation on caller-supplied working data using its settings.
- Step settings follow the
  [configuration-model contract](#runtime-context-and-component-settings).
  Invocation state remains mutable and belongs to the step context.
- The operation may modify the working data.
- Step composition preserves the identity of the caller's working data.

#### Reusable step computations

- A step operation can run with caller-supplied working data and invocation
  context, independently of the complete invocation lifecycle.
- At the middle [API level](#concepts-and-responsibilities), the operation
  receives configuration through its invocation context. Direct calls need no configured step instance; the caller owns context
  attachment, completion, and exception recording. The operation can record
  failures explicitly.
- Steps that select or publish existing results need no numerical API of their
  own. Steps that calculate can reuse
  [analysis computations](#reusable-analysis-computations) or numerical utilities.

#### Invocation contexts

- Invocation contexts let callers inspect an operation's outcome and retrieve
  its published payload.
- An invocation record is available while the operation runs and after it ends.
- The context records settings, completion, failures, and any published payload.
  A payload may reference existing data through a view. Each invocation starts
  with a fresh [artifact context](#artifact-retention-and-composition).
- Normal return marks an invocation complete only when it has no recorded
  failures. An unhandled operation error is recorded and propagated to the caller.
- User interruption and process termination propagate without being classified
  as operation failures.
- Completion records the outcome of the invocation. It does not certify later
  evaluation of deferred results.
- Context payloads follow [lazy data and resource ownership](#lazy-data-and-resource-ownership).

#### Sequential execution and failure handling

- A sequential pipeline provides execution over shared working data in a
  configured order, without deriving a schedule from step dependencies.
- The application orders enabled steps so that producers precede consumers that
  require their outputs. This order may also sequence independent steps.
- The pipeline invokes enabled steps in that order. A normal return permits the
  sequence to continue even when the invocation records failures. A propagated
  error stops the sequence.
- Invocation outcomes follow [invocation contexts](#invocation-contexts).
  Each consumer determines whether available inputs satisfy its requirements;
  the application determines whether the workflow outcome was achieved.
- This driver provides no implicit retry or rollback. Its continuation policy
  does not constrain other execution drivers.

#### Context identity and serialization

- Context identity distinguishes records from different operations and aliases.
  Context serialization supports explicit export and restoration of those records.
- A context identifies its producing operation and invocation alias, if any.
  Creating another operation or alias does not change that identity.
- Reinvocation exposes the latest record for that operation and alias. Retaining
  execution history is a separate responsibility.
- Context export produces a serialized value and leaves the attached live record
  unchanged.
- Restoring an exported context requires the known producing operation.
- A context supports pickle transport to another process for inspection and
  further diagnostics, including its published diagnostic payload. The receiving
  process must have the defining classes and resources required by that payload.
- Context serialization does not define a scientific product format.

#### Run a processing pipeline

- **Handoff:** prepared working data and configured steps → invocation contexts
  and outputs → application outcome decision.
- Steps may invoke analyses and publish result views for subsequent consumers.
- The application selects an execution driver. When it uses a sequential
  pipeline, execution follows
  [sequential execution and failure handling](#sequential-execution-and-failure-handling).

### External execution

Applications run long computations outside the process that decides to run
them: on compute nodes through a batch scheduler, or as a local process during
development. The deciding process, a service or a script, may stop and restart
while the computation continues. The application owns workloads,
external-process commands, scientific settings and result validation; the
deployment owns site values; Tollan owns placement validation and the job
lifecycle. An optional integration lets an orchestration framework supervise
jobs; the lifecycle does not depend on it. An external process may itself run a
[pipeline](#steps-and-pipelines).

#### Placement policy

- A placement policy lets a deployment decide where workloads run and with
  which resources, independently of the code that requests them.
- An execution profile states, for the workloads it selects, one place to run
  jobs and its policy. A local profile runs jobs on the orchestration host. A
  batch-scheduler profile holds the site's submission values, eligible nodes,
  and the default and maximum resources of one job. Each profile names the
  location of its job records and the environment of its external processes.
- An execution request states what one job needs: the workload name, resources
  and a node selection. Applications embed it in their own configuration.
- Resolution selects the first profile, in declared order, whose workload
  selection matches, and combines it with the request into a job spec. Requested
  resources replace the defaults within the maximum; a local profile accepts only
  a thread limit. Resolution rejects unselected workloads and unaccepted
  requests, and contacts no scheduler.
- A requested node selection only narrows the profile's. The scheduler applies
  the combined selection at submission, where an empty selection fails.
- An optional thread limit for numerical libraries does not exceed the job's
  CPUs and reaches the external process; without it, the process chooses its
  own threading.
- A job spec, created only by resolution, is the request with the profile as
  configured at resolution. A job runs one task on one node, with the resources,
  thread limit and node selection of its spec. A job keeps the spec it was
  submitted with; reattachment and recovery never resolve the
  current policy again.
- Switching a workload between a local and a batch-scheduler profile changes no
  application code.
- Policy settings follow the
  [configuration-model contract](#runtime-context-and-component-settings) and
  compose through [configuration sources](#configuration-sources-and-precedence).

#### Job records and schedulers

- A job record keeps the durable state of one job, so that any process with
  access to it can submit, observe, reattach to or cancel the job. A
  caller-supplied key identifies it within its storage location. It holds the
  job spec, the command and environment, the submission receipt with the
  scheduler's native job ID, and the observed state history.
- Records of batch-scheduler jobs reside on storage visible at the same path to
  the orchestration host, the submission host and the compute nodes.
- Submission is once-only. A repeated submission returns the existing receipt.
  A submission that began without producing a receipt leaves the record
  unresolved: further submission fails until reconciliation, which asks the
  scheduler for jobs carrying the record key and either records the receipt
  found or confirms that none exists and allows submission again.
- A scheduler submits, reports states and cancels. Job states are queued,
  running, completed, failed, canceled and unknown; a terminal state carries the
  exit status when reported. Unknown means the scheduler has no information; it
  is neither failure nor completion.
- A transport carries scheduler commands to the submission host, locally or over
  SSH; a transport failure is reported as such, never as a job state.
- A new process can reattach to a local job as to a batch job, including after
  the job ends.
- Reattachment continues an existing job; recomputation creates a new record.

#### Supervision

- Supervision lets a process wait for a job's outcome and act on it, whether it
  submitted the job or reattached to it. It observes states at a bounded
  interval.
- A job succeeds only when the scheduler reports completion with exit status
  zero and the application's result check accepts the record.
- An unknown state may persist for a bounded grace period; beyond it, supervision
  reports the job unresolved, keeps the record and does not resubmit.
- Explicit cancellation requests termination and confirms a terminal state
  within a bound; a requested cancellation is reported separately from a
  confirmed one. Loss of the supervising process does not cancel the job.
- A new job for the same work starts only after the earlier job is terminal or
  canceled. One owner decides each retry: the supervisor, the orchestration
  framework or the scheduler.

#### Orchestration integration

- The optional integration lets Dagster assets run external processes as
  supervised jobs under Dagster Pipes, with Dagster's reporting and admission.
  Without it, the other layers are fully usable.
- A later orchestration process can reattach to the job and read every message
  and log of the external process. A materialization is reported only after the
  complete messages are read.
- Only explicit run cancellation terminates the job; any other interruption of
  the orchestration process leaves it running for reattachment.
- Admission limits use Dagster concurrency pools; the scheduler enforces shared
  cluster capacity across all submitters.

#### Run a computation on an external scheduler

- **Handoff:** deployment policy and execution request → job spec → job record →
  submission → supervised outcome → application result check.
- The application supplies the execution request, command and result check; the
  deployment supplies the execution profiles.

### Artifacts and visualization

An operation's data context can contain more data than a consumer needs to
persist or exchange. Artifacts collect a selected portion or all of that context
into useful bundles. Visualization is one category of data consumption.

#### Artifact data and specifications

- Artifact specifications define the data selected or assembled for persistence
  or exchange and its representation. Producing data does not automatically
  retain it as an artifact.
- An artifact entry pairs data with its effective specification. The data can
  exist independently of a visualization or exported file.
- Specifications own settings and data-preparation operations. Live data belongs
  to artifact entries, not to the reusable specifications.

#### Visualization construction

- A visualization consumes data in the representation required by its input
  contract and constructs a native presentation object using its settings.
  It can consume an existing result view without a live processing context or
  scientific recomputation.
- The presentation object is itself data and can be retained as an artifact.
- Construction is independent of display, export, and result installation.
  Each concrete visualization defines its input contract and when it loads data.

#### Export and display

- Export and display use an already produced object. They do not repeat its
  construction or the scientific calculation that supplied its inputs.
- The artifact specification owns materialization; the caller supplies the
  destination. Standalone export and product publication use the same operation.
- Writers report successfully written destinations and representations. Failures
  propagate; earlier writes may remain. A product publisher owns its publication
  root, inventory, and commit.

#### Artifact retention and composition

- Artifact retention keeps selected data and its effective specification available
  for later use or export, without recovering the complete operation context.
- A composite specification produces a set of artifacts. Each entry retains its
  effective settings after shared overrides have been applied.
- Artifact contexts provide storage and retrieval by specification type and
  optional alias. Retention shares references; it does not copy or materialize
  objects. Adding an existing type and alias replaces that entry.

#### Use artifacts in a step

- **Handoff:** operation data context and artifact settings → selected data with
  effective specifications → persistence or exchange for subsequent consumption.
- A step retains selected data in its invocation's artifact context. Its typed
  payload remains separately available for downstream computations.
- Step configuration records artifact specifications, not live artifact data,
  as defined under [artifact data and specifications](#artifact-data-and-specifications).
  Transport of live artifacts follows
  [context identity and serialization](#context-identity-and-serialization).

### Database resources

Applications need SQL connections and ORM transactions in scripts, Web requests
and workers. Tollan provides reusable resource management and schema conventions;
applications own their domain schema, queries, and connection policy.

#### Connections and transactions

- A database resource manages connection and transaction lifetimes and provides
  access to table metadata across repeated operations.
- A resource created from a URL owns its engine. A resource wrapping an existing
  engine borrows it, as defined under
  [lazy data and resource ownership](#lazy-data-and-resource-ownership); closing
  the wrapper must not dispose the borrowed engine.
- Each session context creates a fresh session, commits pending work on successful
  exit, rolls it back on error, and closes it in either case. Explicit commits are
  not rolled back by a later failure.
- Operations that share pending work use one explicitly supplied session.
  Nesting session contexts does not combine their transactions.
- Connections and sessions finish before their resource closes. Resource
  construction performs no connection or schema operation; reflection and schema
  creation are explicit operations.

#### Schema conventions

- Shared column declarations give application schemas consistent identities,
  descriptive fields, and time conventions.
- Portable UUID values are generated when omitted and preserved when supplied.
  Application schemas own uniqueness and relationship constraints.
- Timestamps use UTC. Application-supplied event times remain distinct from
  automatic creation and modification times. A local timezone records separate
  context; it does not change the timestamp convention.
- Import workflows preserve historical timestamps and normalize them to UTC.
  Applications own timestamp policies beyond the shared declarations.

#### Actors and attribution

- Actor declarations let applications associate records with portable actor
  identities and stable environment facts. Invocation details belong to runs.
- The application defines its actor model and chooses attribution during writes.
  Shared declarations supply actor references and optional timestamps without
  selecting an actor or opening a transaction.

#### Batch writes and query helpers

- Shared operations write prepared row batches and supply common expressions
  without taking over application validation or transactions.
- SQLite batch upsert uses an explicitly supplied transaction; applications
  prepare relationships and actor attribution first.
- SQLite resources provide integer bitwise aggregates without setup; NULL inputs
  need explicit handling and are never silently discarded.
- Shared SQL expressions cover database-generated timestamps and date and time
  queries, following [schema conventions](#schema-conventions).

### Supporting utilities

Applications repeatedly need common operations that belong to no particular
domain. Supporting utilities provide these operations in one reusable place,
so application components do not maintain separate implementations.

#### File locations and item paths

Applications can retain item paths separately from their storage location.
They combine the two when they need a resolved resource location.

- Item paths are relative descendant paths, following the lexical rule under
  [scientific value types](#scientific-value-types), independently of
  configuration roots and filesystem access.
- A file location owns a resolved local or remote location. Joining literal path
  parts returns a new location under the same base: the base is unchanged, its
  scheme, authority, query and fragment are retained, and no resource is opened
  or checked.

#### Robust summaries of labeled arrays

- A reduction summarizes the samples along one dimension of labeled arrays as
  the median and the median absolute deviation scaled by the Gaussian
  consistency factor (1 / Φ⁻¹(3/4)), with the same precision as Astropy's
  `mad_std`. The scatter describes the samples, not the uncertainty of the
  median.
- Attributes, units and coordinates independent of the dimension are retained;
  NaNs propagate. Dimension membership is checked when called, and the numerical
  work stays lazy.

#### Keyed registries

Components publish named capabilities for later lookup without replacing
definitions supplied by another component. A keyed registry owns insertion and
duplicate detection; the registering component owns entry validation.

- Registration rejects every existing key, including an identical repeat, and
  leaves the previous contents unchanged.
- Lookup exposes subsequent registrations in insertion order. Public mapping
  operations must not allow assignment or removal of entries.
- The registry retains supplied values without copying or validating them.
  Applications validate their definitions before registration; constructing or
  validating a definition does not itself register it.
- Automatic registration must use the same insertion operation as explicit
  registration. Domain-specific matching, inheritance, and schema rebuilding
  remain outside the keyed registry.

#### Specification traceability

- Packages trace their contract tests to the sections of their specification,
  so a removed or renamed requirement surfaces as a collection error instead of
  tests that protect nothing.
- A section name is the heading text in lowercase with hyphens. The document
  title is not a section; two headings with the same name are an error.
- Each contract test cites one or more sections on the test itself. Collection
  fails when a test cites a section the specification does not have, when a
  citation names no section, or when a citation is placed on a module or class.
  Uncited tests run normally and protect no requirement.
- A report lists the tests per section, the sections without a test and the
  number of uncited tests. The specification path is configurable.

#### Runtime generic bindings

- Runtime generic bindings let frameworks derive concrete types from generic
  declarations instead of requiring parallel runtime declarations.
- Binding resolution evaluates inherited generic arguments for a specified
  generic ancestor.
- The consuming framework determines which bindings must be concrete and how
  resolved types are used.
- Creating a subclass must not change another class's resolved bindings or
  producer ownership.
