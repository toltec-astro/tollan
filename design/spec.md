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
- Wrapping a borrowed source does not transfer responsibility for its resources
  to Tollan.
- Configuration, execution state, and scientific results are distinct objects
  with distinct lifetimes.

Analyses and steps separate complete workflows from reusable computations:

| API level | Responsibility |
| --- | --- |
| High | Prepare and execute a complete configured operation, including its result or invocation lifecycle. |
| Middle | Adapt domain inputs, apply settings, combine computations, and assemble results through the domain's data interchange contract. |
| Low | Compute from numerical inputs and explicit parameters, independently of configuration models, views, mappers, output namespaces, and invocation contexts. |

- Method binding follows the data interchange protocol. A middle-level method
  may use instance-owned settings or receive settings and context explicitly as
  a classmethod. Both serve the same API level.
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
- A view may expose a descendant of its source through a subview. It caches
  that subview to avoid constructing it on each access.
- A view assumes that its bound source remains valid for its lifetime. It does
  not detect source changes, refresh cached state, or rebind itself. The component
  that changes the source is responsible for managing affected view lifetimes.
- The concrete accessor defines compatibility validation and the operations that
  require additional validation.

#### Backend adapters

- Backend adapters expose schema-based access through each container's native
  data model.
- An adapter implements entity resolution and access for its backend.
- Hierarchical access uses an explicitly selected source scope. View boundaries
  follow [accessors and views](#accessors-and-views).
- Container conversion preserves the selected data's meaning. Its contract states
  whether the result is independently editable and whether conversion requires
  evaluating deferred data.

#### Model tables

- Model tables collect selected object attributes into a mutable, flat workspace
  for filtering and incremental enrichment. They do not require a shared model
  class or reconstruct the input objects.

##### Attribute projection

- Applications declare attribute paths, output representations, and query
  vocabulary. Projection reads only the declared attributes and preserves input
  row order. It does not serialize the input objects.
- Column projection rejects boolean, integer, floating-point and complex storage
  that changes converted values or replaces nulls with values. Converters own
  intentional value changes; storage must not add truncation, overflow or
  precision loss.

##### Incremental enrichment

- Different projections may populate the same destination column from different
  attributes and conversions. Sharing a destination does not require merging
  the input projections or making their readers identical.
- Enrichment updates explicitly addressed rows, preserves unrelated information,
  and lets new null values replace earlier values. It does not synchronize changes
  back to the objects used for projection.
- Missing-attribute fallbacks belong to the input projection. They do not fill
  untouched rows. Omitting a destination preserves its existing values; projecting
  a null replaces them.
- Existing destination columns retain their storage types. Incompatible writes
  raise rather than silently widening storage to arbitrary objects. Newly added
  columns use their declared types and represent untouched rows as missing.
- Copying and in-place enrichment are explicit choices. In-place assignment is
  not transactional; an assignment failure can leave earlier columns updated.

##### Reusable projection declarations

- Annotation-based declarations prepare column mappings without reading object
  values. The resulting projections are reusable across batches; actual reads
  remain duck-typed rather than dispatched by model class.
- Known incompatible annotations can fail declaration before any objects are
  read. Annotations do not replace checks on the projected values.

##### Ordered record rules

- Reusable ordered rules classify records from scalar and collection-valued
  fields, producing one result per record.
- Generic result types constrain rule values at declaration. The unmatched
  default may be null independently of the rule-value type.
- Record values come from mapping keys or object attributes. Batch evaluation
  reads table columns with the same matching semantics.
- The first matching partial mapping wins. Unmatched records receive the
  configured default; per-call overrides do not mutate the mapper.
- Missing fields cannot satisfy constraints. Nulls match an explicit null
  constraint.
- Plain constraints test scalar equality. Explicit collection-membership
  constraints test exact elements; they do not interpret substrings or patterns.
  Missing, null and empty collections do not match. Non-null noncollection
  values raise rather than being treated as unmatched collections.
- Scalar and column-wise evaluation agree and preserve result objects without
  modifying inputs.

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

#### Lazy data and resource ownership

- Lazy access lets callers select data and defer computation without loading the
  entire source. Resource ownership defines who keeps that work executable.
- Tollan does not trigger computation or fetch all source data when the requested
  operation does not require it.

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
- Each source list has independent ordering. Resolver order bounds constrain
  immediate entries only; a nested list contributes at its enclosing source's
  position. Reusing validated sources must not change this rule.
- Relative source-file references resolve against a supplied base directory or
  the working directory. References in a YAML source list resolve against that
  file's directory, including references inside inline nested lists. Validation
  must not open referenced files or rewrite paths inside settings dictionaries.
  The source-file root and the application-value root are independent validation
  settings; neither substitutes for the other.
- Evaluation context supplies values used to select or evaluate settings.
- Callers can refresh settings from external sources separately from evaluating
  settings for a particular input.

#### Scientific value types

- Scientific field types make physical values and resource locations usable in
  validated configuration and metadata models.
- A field serializer produces the representation used to restore the validated
  value. The representation need not preserve the original input syntax.
- Relative descendant paths follow one lexical contract in configuration fields
  and subtree mappings. Validation does not require a containing root to exist,
  performs no filesystem access, and does not establish symlink containment.
- Descendant paths use POSIX syntax and normalize redundant separators and
  current-directory components. They exclude rooted paths and parent traversal.
  The root itself is excluded unless the declaration permits searching the
  containing directory as well as its descendants.
- Time serialization preserves precision independently of display settings.
- Callers can inspect declared defaults without instantiating a configured
  component or executing code that generates a default value.

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
  [configuration integration](#configuration-integration).
- The application supplies evaluation context before constructing components
  whose settings depend on it.


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
- Deferred execution follows
  [lazy data and resource ownership](#lazy-data-and-resource-ownership).

#### Reusable analysis computations

- Reusable computations let callers calculate with the same analysis settings
  without preparing an output namespace or running the complete workflow.
- The [three API levels](#concepts-and-responsibilities) apply to analyses:
  the high level prepares inputs and an output scope; the middle level adapts
  domain inputs and configuration to computations and assembles their results.
- Result integration is also a middle-level responsibility. The shared analysis
  base validates, reuses, and installs results with their producing configuration.
  A focused computation can instead return a standalone result.

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
  [inputs and output scopes](#inputs-and-output-scopes).
- If a step invokes the analysis, the step records execution separately from the
  analysis's producing configuration.


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
- The [three API levels](#concepts-and-responsibilities) apply to steps:
  the high level owns context creation and outcome recording; the middle level
  selects inputs, combines computations, installs results, and publishes payloads.
- The middle-level operation receives configuration through its invocation
  context. Direct calls need no configured step instance; the caller owns context
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
  A payload may reference existing data through a view.
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
- Each invocation receives a fresh artifact context. Configuration records retain
  artifact settings and omit live objects. Transport of live artifacts follows
  [context identity and serialization](#context-identity-and-serialization).

### Database resources

Applications need SQL connections and ORM transactions in scripts, Web requests
and workers. Tollan provides reusable resource management and schema conventions;
applications own their domain schema, queries, and connection policy.

#### Connections and transactions

- A database resource manages connection and transaction lifetimes and provides
  access to table metadata across repeated operations.
- A resource created from a URL owns its engine. A resource wrapping an existing
  engine borrows it; closing the wrapper must not dispose the borrowed engine.
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

- Shared database operations support prepared row batches and commonly needed
  expressions without taking over application validation or transactions.
- SQLite batch upsert uses an explicitly supplied transaction. Applications
  prepare relationship handling and actor attribution before writing.
- SQLite resources provide integer bitwise aggregates without application setup.
  NULL inputs require explicit handling; aggregates must not silently discard them.
- Shared SQL expressions support database-generated timestamps and date/time
  queries. Timestamp ownership follows [schema conventions](#schema-conventions).

### Supporting utilities

Applications repeatedly need common operations that belong to no particular
domain. Supporting utilities provide these operations in one reusable place,
so application components do not maintain separate implementations.

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

#### Runtime generic bindings

- Runtime generic bindings let frameworks derive concrete types from generic
  declarations instead of requiring parallel runtime declarations.
- Binding resolution evaluates inherited generic arguments for a specified
  generic ancestor.
- The consuming framework determines which bindings must be concrete and how
  resolved types are used.
- Creating a subclass must not change another class's resolved bindings or
  producer ownership.
