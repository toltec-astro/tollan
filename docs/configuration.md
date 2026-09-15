# Runtime configuration and domain handlers

`RuntimeContext` loads ordered sources, evaluates their conditions, and merges
default and override tiers. `ConfigHandler` consumes that configuration: it
extracts one domain, validates a Pydantic model at construction, and owns the
resources built from those settings.

## Define a handler

```python
import re
from functools import cached_property
from typing import Literal

from pydantic import BaseModel
from tollan.config import ConfigHandler, RuntimeContext, SubConfigKeyTransformer


class SearchConfig(BaseModel):
    pattern: str


class SearchHandler(
    SubConfigKeyTransformer[Literal["search"]],
    ConfigHandler[SearchConfig],
):
    @cached_property
    def compiled_pattern(self):
        return re.compile(self.config.pattern)


rc = RuntimeContext()
rc.update_default_config({"search": {"pattern": "error"}})
handler = SearchHandler(rc)  # Validates SearchConfig now.
assert handler.compiled_pattern.search("an error occurred") is not None
```

Use ordinary `cached_property` for handler-owned resources. Creating another
handler gives it separate property caches; updating a runtime does not invalidate
an existing handler's config or resources. Keep expensive resource construction
out of config validation itself.

The handler takes a runtime, not a raw dictionary or an already validated model.
For in-memory use, configure the runtime's tiers or supply a dictionary source.
The private runtime reference is a provider for creating new handlers, not the
current handler's source of settings. Application code should consume
`handler.config` for domain settings and `handler.runtime_info` for the broader
execution context, including invocation details and validation context.

Both are captured at construction from the same validated runtime configuration.
Later runtime updates do not replace an existing handler's runtime-info model.
Treat that model as read-only; its `config_sources` field is a shared reference
for introspection, not a frozen copy of the source tree.

## Temporary variants

```python
with handler.temporary_config(overrides={"pattern": "warning"}) as other:
    assert other.compiled_pattern.search("a warning occurred") is not None
    assert handler.config.pattern == "error"

with handler.temporary_runtime_config(
    overrides={"search": {"pattern": "critical"}},
    validation_context={"job_id": 42},
) as other:
    assert other.config.pattern == "critical"
    assert other.runtime_info.validation_context["job_id"] == 42
    assert "job_id" not in handler.runtime_info.validation_context
```

Both methods yield a new handler. `temporary_config` wraps domain-shaped patches
using `prepare_runtime_config_data`; `temporary_runtime_config` accepts the full
runtime shape. Both support `defaults=`, `overrides=`, and `validation_context=`.
Patches merge recursively through `rupdate`, including its list selectors.

Defaults remain below user sources; overrides remain above them. The context
patch merges into the inherited context and is used for source conditions and
Pydantic validation. Each variant has its own default, override, and info tiers,
validation context, and merged-config caches. Nested and concurrent scopes do
not temporarily mutate the parent runtime or swap the original handler's state.

Raw configuration is validated afresh, rather than patching a dump of the old
model. Consequently, a relative path can be resolved under a different
`validation_context={"rootpath": ...}` without retaining its old expansion.

The context manager does not automatically close arbitrary resources or make
the yielded handler unusable on exit. Resource-specific cleanup belongs to the
concrete handler or caller.

## Recreate from a changed runtime

```python
rc.update_override_config({"search": {"pattern": "new"}})
new_handler = handler.recreate()
assert new_handler.config.pattern == "new"
assert handler.config.pattern == "error"
```

`recreate()` uses the attached runtime's **current** configuration. Temporary
variants also start from the current runtime tiers, not from the original
handler's validated model. Retain the original handler when you need its original
settings. The handler stores no second raw config dictionary and has no in-place
config-update or auto-cache-reset API.

Treat validated config models and loaded source data as read-only. The config
property is read-only, but neither it nor Pydantic's frozen-model option provides
deep immutability for nested objects. Container isolation applies to updates
through the runtime APIs; arbitrary direct mutation of shared nested values is
not protected.

## YAML configuration files

A YAML mapping supplies configuration values directly. A YAML list supplies
source declarations, which are validated as a `ConfigSourceList`:

```yaml
- source: base.yaml
- enable_if: workers >= 4
  source:
    search:
      pattern: warning
```

Load either form through `RuntimeContext(config_sources=Path("config.yaml"))`.
For a directory, numbered files such as `00_base.yaml` and `10_overrides.yaml`
are loaded in numeric order; each file may contain a mapping or a source list.

Within each source list, omitted orders follow list position; explicit orders
must be unique within that list. Lists can contain nested lists through their
`source` values. Each nested list has its own ordering.

File references in declarations are relative to the containing YAML file,
including references inside inline nested lists. YAML and `.env` formats are
inferred from the file suffix unless `format` is explicit. These references
identify sources to load; they are not part of the configuration data.

Path-valued configuration data stays unchanged until typed model validation.
Tollan's path types use `validation_context["rootpath"]` at that point. Including
a file does **not** make its path-valued settings relative to its own directory:
after merging, they use the same validation root as the other settings. Source
file locations are not retained as per-value path bases.

Parsed mappings and source lists are cached, but conditions and merging run for
each load's context. Disabled file sources are not read. Reloading the runtime
discards cached YAML source lists and reads their included files afresh.

Empty files, YAML null, and empty mappings/lists supply no settings. Other scalar
documents and invalid source declarations raise errors rather than being ignored.

## Conditional sources

An `enable_if` expression selects a source using variables from a context dictionary.
Expressions use
[pandas query syntax](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.query.html):
`&`, `|`, `~`, `in`, and `not in` are supported, with comparisons binding
before boolean combinations.

```python
from tollan.config.sources import DictConfigSource

source = DictConfigSource(
    order=0,
    source={"logging": {"level": "DEBUG"}},
    enable_if='workers >= 4 & environment in ["staging", "production"]',
)
assert source.is_enabled_for({"workers": 8, "environment": "production"})
assert not source.is_enabled_for({"workers": 2, "environment": "production"})
```

No context or an undefined variable disables a conditional source. Other query
errors propagate so malformed expressions are visible. Evaluation is not guaranteed
to short-circuit: `workers >= 4 | missing > 0` is disabled even if `workers` is 8.
Supply the variables required by an expression before evaluating its conditions.

Expressions must come from trusted configuration: pandas query evaluation can
execute code and is not a sandbox. The context API accepts a dictionary of variable
bindings, not a DataFrame.

## Runtime variants and source caching

`rc.with_config(defaults=..., overrides=..., validation_context=...)` returns a
new runtime directly, using the same mechanism as handler variants. No handler
or domain extraction is needed for this lower-level operation.

Related runtimes share the same user-source objects. YAML and env-file sources
cache their read-and-parse results by default, so creating a variant does not
reread a cached file. Dictionary sources return their in-memory data without
caching. Nested source lists evaluate conditions and merge their contents for each
context; their merged results are not cached. Env-file interpolation uses the
environment at read time and is refreshed when that source is invalidated.

Use `source.enable_cache(enabled=False)` to read a file on every load.
`rc.config_sources.enable_cache(predicate=..., exclude=...)` selects which
immediate sources cache their reads; unselected sources have caching disabled.
A selected nested list forwards its cache setting to its contents. Creating a
runtime variant preserves these settings. Changing a shared source's cache
setting affects all runtimes using that source.

`rc.reload()` explicitly invalidates source caches and reloads that runtime. Source
cache invalidation is shared with related variants, but their already materialized
config models and existing handlers do not change. Construct a fresh handler after
reloading to consume the new configuration. The older `rc.set_context()` mutates
one runtime temporarily and restores its saved config caches; use variants when
scopes may overlap concurrently.

Validation uses Pydantic's documented
[`model_validate(..., context=...)` interface](https://docs.pydantic.dev/latest/concepts/validators/#validation-context).
User patches go through validation, not unvalidated model-copy updates.
