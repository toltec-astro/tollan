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
| Data access | Map names and expose typed views over supported containers. | {doc}`schema-mapping-accessors`, {doc}`data-adapters` |
| Model tables | Project object attributes, enrich rows, and query a pandas table. | {doc}`model-tables` |
| Configuration | Load settings, validate values, and configure components. | {doc}`configuration`, {doc}`validation-types` |
| CLI | Add commands, help, logging, and configuration options. | {doc}`cli` |
| Analyses and results | Apply configured calculations and inspect their results and producing settings. | {doc}`analyses` |
| Pipelines | Run configured steps and inspect execution results. | {doc}`pipelines` |
| Artifacts and visualization | Select data for persistence or exchange; construct and display figures. | {doc}`artifacts` |
| Databases | Manage connections and transactions; define shared column and actor conventions. | {doc}`databases` |
| Utilities and plotting | Work with files, YAML, units, logging, and figures. | {doc}`utilities` |
| Generic classes | Bind schemas, mappers, and models to subclasses. | {doc}`generic-runtime-bindings` |

```{toctree}
:maxdepth: 1
:caption: Data access

schema-mapping-accessors
data-adapters
model-tables
```

```{toctree}
:maxdepth: 1
:caption: Application configuration

configuration
validation-types
cli
```

```{toctree}
:maxdepth: 1
:caption: Analysis and execution

analyses
pipelines
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
:caption: Reference

models
modules
```

# Indices and tables
* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
