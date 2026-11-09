# Tollan

Tollan provides schema-based data access, validated application configuration,
typed pipeline steps, and scientific Python utilities. Start with installation
and the quick start, then choose a guide for your task.

Version: {sub-ref}`release`.

```{toctree}
:maxdepth: 1
:caption: Getting started

readme
```

## Choose a domain

| Domain | What you can do | Guide |
| --- | --- | --- |
| Data access and representation | Map names, expose typed views over supported containers, and build and query model tables. | {doc}`schema-mapping-accessors`, {doc}`data-adapters`, {doc}`model-tables` |
| Application configuration | Load settings, validate values, and configure components. | {doc}`configuration`, {doc}`validation-types` |
| Command-line applications | Add commands, help, logging, and configuration options. | {doc}`cli` |
| Analyses and results | Apply configured calculations and inspect their results and producing settings. | {doc}`analyses` |
| Steps and pipelines | Run configured steps and inspect execution results. | {doc}`pipelines` |
| External execution | Declare where workloads run, then run, follow and cancel jobs locally, on Slurm, or from Dagster. | {doc}`execution` |
| Artifacts and visualization | Select data for persistence or exchange; construct and display figures. | {doc}`artifacts` |
| Database resources | Manage connections and transactions; define shared column and actor conventions. | {doc}`databases` |
| Supporting utilities | Work with files, YAML, units, logging, and figures; bind schemas, mappers, and models to subclasses. | {doc}`utilities`, {doc}`generic-runtime-bindings` |

```{toctree}
:maxdepth: 1
:caption: Data access and representation

schema-mapping-accessors
data-adapters
model-tables
```

```{toctree}
:maxdepth: 1
:caption: Application configuration

configuration
validation-types
```

```{toctree}
:maxdepth: 1
:caption: Command-line applications

cli
```

```{toctree}
:maxdepth: 1
:caption: Analyses and results

analyses
```

```{toctree}
:maxdepth: 1
:caption: Steps and pipelines

pipelines
```

```{toctree}
:maxdepth: 1
:caption: External execution

execution
```

```{toctree}
:maxdepth: 1
:caption: Artifacts and visualization

artifacts
```

```{toctree}
:maxdepth: 1
:caption: Database resources

databases
```

```{toctree}
:maxdepth: 1
:caption: Supporting utilities

utilities
```

```{toctree}
:maxdepth: 1
:caption: For developers

extending-mappers
```

```{toctree}
:maxdepth: 1
:caption: Reference

models
modules
```

# Indices and tables
* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
