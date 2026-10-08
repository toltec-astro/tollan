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
| Data access | Map names, expose typed views, and store analysis results. | {doc}`schema-mapping-accessors`, {doc}`analyses` |
| Configuration | Load settings, validate values, and configure components. | {doc}`configuration`, {doc}`validation-types` |
| CLI | Add commands, help, logging, and configuration options. | {doc}`cli` |
| Pipelines | Run configured steps and inspect execution results. | {doc}`pipelines` |
| Utilities and plotting | Work with files, YAML, units, logging, and figures. | {doc}`utilities` |
| Generic classes | Bind schemas, mappers, and models to subclasses. | {doc}`generic-runtime-bindings` |

```{toctree}
:maxdepth: 1
:caption: Data access

schema-mapping-accessors
data-adapters
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
