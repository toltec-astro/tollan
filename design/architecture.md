# Tollan architecture

Settled implementation mechanisms that realize contracts in `spec.md`. This
record describes the current code; the specification owns the contracts.

## Data access

- **Selected nodes are cached on the view.** An accessor or view computes the
  node it presents (`data_source`) once, with `functools.cached_property`, from
  the supplied scope. This realizes "a view may expose a descendant of its
  source" without searching again on each access; it is valid because a view
  does not refresh or rebind.
- **Mapper pickling keys bindings by schema field name.** A mapper's schema is
  one instance per schema class in each process, and a mapping without value
  equality compares by identity. `Mapper.__getstate__` therefore stores each
  binding under the name of its schema field, and `__setstate__` looks the
  mapping up on the receiving process's schema. Bindings outside the schema keep
  their mapping object. `MISSING` pickles by reference, so restored bindings
  compare with the receiving process's sentinel.

## Configuration

- **File sources cache parsed contents.** A file source keeps its parsed data in
  a cached property; conditions and merging run on every load. Runtime variants
  share the source objects and therefore their reads; `RuntimeContext.reload()`
  clears them. Measured on 12 KB of production YAML (2026-11-08): 0.64 ms per
  variant with the cache, 19.9 ms without.

## External execution

- **The local scheduler writes the exit status into the job record.** The
  detached shell wrapper writes `exit_status` atomically (temporary file, then
  rename) when the command ends, so a process that did not start the job reads
  the terminal state from the record.
- **Dagster Pipes files live in the job record.** The Pipes context
  (`pipes_context.json`) and the external process's messages
  (`pipes_messages.jsonl`) are files in the job record directory. A reattaching
  orchestration process reads them from there, and results are reported only
  after the external process has closed its messages.
