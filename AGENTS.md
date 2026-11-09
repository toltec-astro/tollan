# Tollan agent guide

Tollan is domain-neutral infrastructure for scientific Python applications:
schema-based data access, model tables, validated configuration, command-line
applications, analyses, steps and pipelines, external execution, artifacts,
database resources and supporting utilities. Zhiyuan Ma
<zhiyuanma@umass.edu> is the maintainer.

## Read first

1. `design/spec.md`: the contract. Its section outline is the outline of the
   user guides in `docs/`.
2. `design/decisions/`: the decision records. Only records with
   `status: "accepted"` are binding.
3. `design/architecture.md`: settled mechanisms that realize the contracts.
4. `docs/`: the user guides, one per domain, and the API reference.

## Ownership

- Tollan owns the reusable mechanisms: mappers, accessors and views; model
  tables and record rules; configuration sources, runtime contexts and field
  types; the CLI base; analysis, step and pipeline contracts; the external
  execution lifecycle; artifact contexts; database resources and conventions;
  registries and generic bindings.
- Applications own domain semantics: schemas for their data, workloads and
  scientific settings, their database schemas and queries, and their policies.
  Deployments own site values such as execution profiles.
- Tollan text, code, examples and tests use neutral names. They do not name an
  application, an instrument or its data.

## Development

- Tests: `uv run --locked pytest`. A contract test cites the specification
  sections it protects with `@pytest.mark.spec("<section>")` on the test
  itself, only when its assertions stay within those sections. Tests of a single
  object's documented semantics or of the implementation stay uncited.
  `--spec_report` lists tests per section.
- QA: `just qa`. Documentation: `just doc-build` (strict, nitpicky) and
  `just doc-test` (executes the guide examples).
- Performance: `just benchmark-save` and `just benchmark-check <baseline>`.
- Follow the workspace rules and the `design-records`, `workflow-contract-audit`
  and `agent-technical-writing` skills. Do not copy their text here.
