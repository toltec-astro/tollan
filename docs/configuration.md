# Configure an application

Use `RuntimeContext` to load configuration and `ConfigHandler` to validate the
settings used by a component. A handler keeps its validated settings and any
resources it creates, even if the runtime is updated later.

## Add configuration options to a CLI

Use `RuntimeContext.add_cli_options()` to add `--config_paths` (or `-c`) and
`--env_paths` to a command or group callback. Construct the runtime inside your
callback with `from_cli_ctx()`:

```python
import typer

from tollan.config import RuntimeContext
from tollan.utils.typer import create_cli

app = create_cli(version="1.0")


@app.callback()
@RuntimeContext.add_cli_options()
def main(ctx: typer.Context, profile: str = "default"):
    rc = RuntimeContext.from_cli_ctx(ctx)
    rc.update_default_config({"profile": profile})
    ctx.obj = rc


@app.command()
def show(ctx: typer.Context):
    print(ctx.obj.config_dict.get("profile"))


if __name__ == "__main__":
    app()
```

```console
python app.py --profile local --config_paths settings.yaml -- show
python app.py -c config.d local.yaml --env_paths env.d local.env -- show
```

Each path may be a file or directory. Both options accept several paths at once
or repeated occurrences. Use `--` to end a list of paths before a subcommand or
positional inputs.

Later paths override earlier ones. Within a directory, files such as
`00_defaults.yaml`, `10_site.env`, and `20_local.yaml` load in numeric order;
their numeric prefixes must be unique. Environment paths override configuration
paths, and command-line overrides override both.

To put options on a command instead, apply `add_cli_options()` below
`@app.command()`. `from_cli_ctx()` reads the options on that callback's context;
it does not inherit path options from a parent group. Store the runtime on
`ctx.obj`, as above, when child commands should use the parent's runtime.

The helper also works with `TollanTyper()` for a single-command application.
See [command-line applications](cli.rst) for a command with variadic inputs and
an example accepting dotted configuration overrides.

## Load configuration from Python

Use the same loading rules without Typer:

```python
from pathlib import Path
from tollan.config import RuntimeContext

rc = RuntimeContext.from_cli(
    config_paths=[Path("config.d"), Path("local.yaml")],
    env_paths=[Path("env.d")],
    cli_args=["--search.pattern", "warning"],
)
```

`config_paths` accepts YAML and dotenv files. To select particular formats, pass
a collection of `ConfigSourceFormat` members:

```python
from tollan.config import ConfigSourceFormat

rc = RuntimeContext.from_cli(
    config_paths=[Path("settings.d")],
    config_formats={ConfigSourceFormat.yaml},
)
```

`config_formats=None` accepts all supported formats; an empty collection accepts
none. This filters the supplied paths and directory entries, not explicit
includes inside a YAML file. `env_paths` always selects dotenv files only.
Pass the same `config_formats` setting to `from_cli_ctx()` in a CLI callback.

## Use dotenv values

Request an environment handler when you need to pass configured variables to
another process:

```python
import os

rc, env_handler = RuntimeContext.from_cli(
    env_paths=[Path("local.env")],
    return_env_handler=True,
)
assert env_handler is not None
env = {**os.environ, **env_handler.as_environ()}
# Pass env=env to subprocess.run(...).
```

`as_environ()` returns a fresh `dict[str, str]` containing only the selected
environment section. It does not read or modify `os.environ`. In this example,
configured values override inherited process variables; reverse the merge order
if the process environment should win.

Inside a callback decorated with `RuntimeContext.add_cli_options()`, use:

```python
rc, env_handler = RuntimeContext.from_cli_ctx(ctx, return_env_handler=True)
```

Requesting a handler loads the merged configuration immediately and captures its
environment settings. Later runtime updates do not change that handler. Use
`env_handler.recreate()` to capture updated settings, or
`env_handler.temporary_config(overrides={"PORT": 9000})` for a temporary variant.
Values are converted with Python's `str`, so a YAML integer `8000` becomes
`"8000"` and a Boolean `true` becomes `"True"`. The runtime's original values
are not changed. The selected section must be a mapping with string keys.

Without `return_env_handler=True`, both factories return only the runtime and
leave configuration loading lazy.

### Choose an environment namespace

Dotenv values are stored under `ENV_NAMESPACE_DEFAULT` (`"_env"`), exported
by `tollan.config`. Choose a different namespace when needed:

```python
rc, env_handler = RuntimeContext.from_cli(
    env_paths=[Path("local.env")],
    env_namespace="process",
    return_env_handler=True,
)
assert env_handler is not None
print(env_handler.as_environ()["HOST"])
```

`env_namespace=None` loads the values at the root. The setting also applies to
included dotenv files. A source declaration can override it with
`namespace: custom` or `namespace: null`. `from_cli_ctx()` accepts
`env_namespace` too. The handler reads only the chosen namespace, not sources
explicitly assigned elsewhere. If the chosen section is absent, the handler
contains an empty mapping.

With both `env_namespace=None` and `return_env_handler=True`, the result is
`(rc, None)` and loading stays lazy: root-level environment values are mixed
with application configuration and are not collected into a handler.

YAML can provide defaults or overrides for dotenv values at the same key:

```yaml
_env:
  HOST: localhost
  PORT: "8000"
```

Dotenv interpolation uses that file's values and the process environment when
the file is read. It does not interpolate against merged YAML settings or other
configuration sources. Command-line overrides use YAML value parsing, so quote
a numeric value as a YAML string when its type must remain a string.

## Validate a component's settings

Define a Pydantic model and a handler. `SubConfigKeyTransformer` selects the
component's section of the runtime configuration:

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
handler = SearchHandler(rc)
assert handler.compiled_pattern.search("an error occurred") is not None
```

Construction validates the settings immediately. Use `handler.config` for
validated settings and `handler.runtime_info` for execution information.
Use `cached_property` for expensive resources; each new handler has its own
resource cache.

Runtime defaults apply before loaded sources. Runtime overrides apply after
sources and CLI overrides. For in-memory configuration, set these tiers or
pass a dictionary source to `RuntimeContext`.

## Try temporary settings

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
```

Both methods yield a new handler without changing the original. Use
`temporary_config` for component settings and `temporary_runtime_config` for
the full configuration. Both accept `defaults`, `overrides`, and
`validation_context`; patches merge recursively.

The new handler validates settings with the supplied context. For example,
changing `rootpath` lets path fields resolve under a different directory.
For a runtime without a handler, use
`rc.with_config(defaults=..., overrides=..., validation_context=...)`.

Treat validated models and loaded data as read-only; use these APIs for updates
rather than mutating nested values directly. Leaving a temporary scope does not
close resources automatically: resource cleanup belongs to the handler or caller.

## Apply updated settings

Updating a runtime does not change an existing handler. Create a new handler
when you want to use the updated configuration:

```python
rc.update_override_config({"search": {"pattern": "new"}})
handler_new = handler.recreate()
assert handler_new.config.pattern == "new"
assert handler.config.pattern == "error"
```

`recreate()` and temporary variants use the runtime's current settings, not a
copy of the original handler's settings. Keep the original handler when you
need its previous configuration.

## Include configuration files

A YAML mapping supplies settings directly. A YAML list includes other sources:

```yaml
- source: base.yaml
- source: local.env
- enable_if: workers >= 4
  source:
    search:
      pattern: warning
```

Load either form with `RuntimeContext(config_sources=Path("settings.yaml"))`.
List entries load in order; optional explicit `order` values must be unique
within their list. A disabled source contributes no settings.

Included filenames are relative to the containing YAML file. File formats are
inferred from their suffix unless a declaration specifies `format`.

Paths *inside settings* are different: they remain unchanged until model
validation. Tollan's path types resolve them against
`validation_context["rootpath"]`, not the directory of each included file.
Set that validation root explicitly when your configuration contains relative
paths.

Source lists can be nested. List patches apply to values from preceding sources.
For example, after a source supplies `items: [base]`, this appends `a` and `b`:

```yaml
- source:
    - source: {items: {"[]": [a]}}
    - source: {items: {"[]": [b]}}
```

The result is `items: [base, a, b]`. Disabling the containing source skips both
entries. Empty YAML files contribute no settings; malformed documents raise
errors.

## Select sources with conditions

Use `enable_if` to select a source using context variables. Expressions use
[pandas query syntax](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.query.html),
including `&`, `|`, `~`, `in`, and `not in`:

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

Provide a dictionary containing all variables used in an expression. Missing
context or an undefined variable disables the source; other expression errors
propagate. Do not rely on short-circuit evaluation.

Only use trusted expressions: pandas query evaluation is not a sandbox.

## Reload changed files

File contents and dotenv interpolation are cached. Creating a runtime variant
reuses cached reads but evaluates source conditions for the new context.
Disabled sources are not read.

After editing a configuration file or changing an interpolated environment
variable, reload the runtime and create a new handler:

```python
rc.reload()
handler_new = handler.recreate()
```

Existing handlers retain their settings and resources. Related runtimes share
file caches, but reloading one does not replace another's already loaded
configuration; reload that runtime too when it needs the new values.

For a file that must be read on every load, use
`source.enable_cache(enabled=False)`. For a temporary validation context, prefer
`rc.with_config(validation_context=...)` when scopes may overlap.
