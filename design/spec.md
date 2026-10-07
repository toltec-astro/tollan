# Tollan specification

## Overview

### Purpose and scope

Tollan provides reusable infrastructure for scientific Python applications.
Applications define domain semantics and operational policy. Tollan provides
interfaces that separate those decisions from reusable operations.

### Concepts and responsibilities

- Each domain below defines its own contracts. Integrated workflows specify the
  handoffs between domains without redefining those contracts.
- Wrapping a borrowed source does not transfer responsibility for its resources
  to Tollan.
- Configuration, execution state, and scientific results are distinct objects
  with distinct lifetimes.

## Domains

### Configuration and validation

Scientific applications run the same operations with different input-dependent,
site, and invocation settings. The configuration system supports modular settings
and composition from multiple locations and formats. It provides consistent,
convenient entry points for defaults and overrides. Validation gives each
component typed settings before it uses them.

#### Configuration sources and precedence

- Configuration sources compose modular settings from different locations and
  formats through a common loading interface.
- Source composition defines the order in which settings override earlier values.
- Evaluation context supplies values used to select or evaluate settings.
- Callers can refresh settings from external sources separately from evaluating
  settings for a particular input.

#### Runtime context and component settings

- Runtime configuration supports applying shared settings to input-dependent
  component instances.
- A runtime context maintains the application's configuration sources, overrides,
  and evaluation context.
- A configured component captures validated settings from the runtime.
- Subsequent runtime changes do not alter an existing component's settings.
  Recreating the component captures settings from the updated runtime.

#### Scientific value types

- Scientific field types make physical values and resource locations usable in
  validated configuration and metadata models.
- A field serializer produces the representation used to restore the validated
  value. The representation need not preserve the original input syntax.
- Callers can inspect declared defaults without instantiating a configured
  component or executing code that generates a default value.

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

#### Backend adapters

- Backend adapters expose schema-based access through each container's native
  data model.
- An adapter implements entity resolution and access for its backend.
- Hierarchical access uses an explicitly selected source scope. View boundaries
  follow [accessors and views](#accessors-and-views).
- Container conversion preserves the selected data's meaning. Its contract states
  whether the result is independently editable and whether conversion requires
  evaluating deferred data.

#### Accessors and views

- An accessor combines a source and mapper into a domain API.
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

#### Units and table conversion

- Unit and table adapters let scientific consumers use Astropy quantities and
  quantity-aware tables with data stored in other containers.
- Their scope is the conversion between numeric arrays with unit metadata and
  Astropy representations; source containers need not store Astropy objects.
- Quantity access interprets the source's unit metadata and presents values with
  their physical units.
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

### Analyses and results

Scientific users apply configured calculations to selected data, compare results,
and inspect computed outputs. Analyses associate results
with the settings that produced them. Result access is independent of the
application that scheduled the calculation.

#### Inputs and output scopes

- Input selection and output scopes let analyses operate within a larger data
  hierarchy without taking ownership of unrelated data.
- An analysis receives selected inputs and an output scope.
- The analysis identifies the outputs it owns. Outputs can use independent
  coordinate systems without constraining one another.
- Output installation preserves data outside the owned locations.

#### Computation and producing configuration

- Producing configuration associates a scientific result with the settings used
  to calculate it.
- Analysis configuration supplies the parameters used by the computation.
- Installed results retain the configuration used to produce them. Later changes
  to application settings do not change that recorded configuration.
- Deferred execution follows
  [lazy data and resource ownership](#lazy-data-and-resource-ownership).

#### Result views

- A result view resolves analysis outputs and their producing configuration.
- Constructing a result view requires the result data and metadata, not the
  original pipeline invocation.
- View lifetime follows [accessors and views](#accessors-and-views).

#### Result reuse and replacement

- Result reuse avoids repeating a calculation when an existing result satisfies
  the requested analysis. Replacement updates results within the analysis scope.
- The concrete analysis defines the conditions for reusing an existing result.
  Configuration equality alone does not establish input equivalence.
- Replacement applies to the analysis-owned output locations defined under
  [inputs and output scopes](#inputs-and-output-scopes).

### Steps and pipelines

Processing applications combine steps whose input and output requirements form
a dependency graph. Steps expose operations and invocation records; an execution
driver determines their scheduling. A sequential pipeline is one driver: it uses
an application-supplied order to accommodate those dependencies. Step contracts
are independent of this strategy and permit other drivers, including scheduling
by a directed acyclic graph (DAG).

#### Steps and configuration

- A step invokes an operation on caller-supplied working data using its settings.
- The operation may modify the working data.
- Step composition preserves the identity of the caller's working data.

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
- Context restoration requires the known producing operation.
- Context serialization does not define a scientific product format.

### Command-line applications

Applications need consistent command-line entry points without repeating common
CLI setup. Tollan provides a specialized Typer class for this purpose, so each
application can concentrate on its commands and their behavior.

#### Configuration integration

- Configuration integration gives command-line applications access to the shared
  runtime configuration system.
- It translates selected arguments into inputs to
  [configuration sources and precedence](#configuration-sources-and-precedence).

### Supporting utilities

Applications repeatedly need common operations that belong to no particular
domain. Supporting utilities provide these operations in one reusable place,
so application components do not maintain separate implementations.

#### Runtime generic bindings

- Runtime generic bindings let frameworks derive concrete types from generic
  declarations instead of requiring parallel runtime declarations.
- Binding resolution evaluates inherited generic arguments for a specified
  generic ancestor.
- The consuming framework determines which bindings must be concrete and how
  resolved types are used.
- Creating a subclass must not change another class's resolved bindings or
  producer ownership.

## Integrated workflows

### Configure and launch an application

- **Handoff:** application arguments and selected sources → runtime → configured
  component → application callback.
- CLI arguments enter the runtime through
  [configuration integration](#configuration-integration).
- The application supplies evaluation context before constructing components
  whose settings depend on it.

### Read and inspect scientific data

- **Handoff:** opened or borrowed source → mapper → accessor → requested values.
- The application chooses the source and concrete reader. Validation follows
  [accessors and views](#accessors-and-views).
- Borrowed and owned resources follow
  [lazy data and resource ownership](#lazy-data-and-resource-ownership).

### Compute and inspect analysis results

- **Handoff:** selected input view and settings → analysis output scope → result view.
- The caller selects inputs and an output scope as defined under
  [inputs and output scopes](#inputs-and-output-scopes).
- If a step invokes the analysis, the step records execution separately from the
  analysis's producing configuration.

### Run a processing pipeline

- **Handoff:** prepared working data and configured steps → invocation contexts
  and outputs → application outcome decision.
- Steps may invoke analyses and publish result views for subsequent consumers.
- The application selects an execution driver. When it uses a sequential
  pipeline, execution follows
  [sequential execution and failure handling](#sequential-execution-and-failure-handling).
