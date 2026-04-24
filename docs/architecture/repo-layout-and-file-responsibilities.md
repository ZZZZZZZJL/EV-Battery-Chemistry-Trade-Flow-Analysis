# Repo Layout And File Responsibilities

## Final Public Repo Layout

```text
EV-Battery-Chemistry-Trade-Flow-Analysis
|-- .github/
|-- .codex/
|-- .env.example
|-- .gitignore
|-- pyproject.toml
|-- README.md
|-- render.yaml
|-- apps/
|   `-- web/app.py
|-- configs/
|-- docs/
|-- schemas/
|-- scripts/
|-- tests/
|-- fixtures/
`-- src/trade_flow/
    |-- baseline/
    |-- conversion_factor_optimization/
    |-- domain/
    |-- legacy_site/
    |-- metals/
    |-- optimization/
    |   |-- common/
    |   `-- conversion_factor/
    |-- pipelines/
    |-- publishing/
    |-- runtime/
    |-- utils/
    `-- web/
```

## Directory Roles

- `apps/web/`
  Only public ASGI entrypoint. Local dev and Render should both import `apps.web.app:app`.
- `configs/`
  Human-readable app, environment, and metal metadata skeletons.
- `schemas/`
  Public runtime contract definitions for bundle, manifest, and payload formats.
- `src/trade_flow/domain/`
  Shared runtime path conventions, manifest models, enums, validation helpers, and contract types.
- `src/trade_flow/web/`
  Canonical web surface: FastAPI app, API routes, presenters, templates, and static assets.
- `src/trade_flow/runtime/`
  Runtime bundle loading, dataset registry, payload builders, and repository access.
- `src/trade_flow/baseline/`
  Baseline trade-flow analysis logic.
- `src/trade_flow/conversion_factor_optimization/`
  The only official first-generation optimization engine implementation.
- `src/trade_flow/optimization/`
  Stable optimization-facing namespace for shared helpers and conversion-factor wrappers.
- `src/trade_flow/metals/`
  Shared metal-adapter model and per-metal extension points.
- `src/trade_flow/pipelines/`
  High-level baseline, optimization, and snapshot pipeline facades.
- `src/trade_flow/publishing/`
  Runtime bundle build, validate, and publish helpers.
- `src/trade_flow/legacy_site/`
  Temporary internal compatibility namespace for residual viewer services. This is not a public product package and should be removed once remaining imports are migrated into the canonical modules.
- `scripts/`
  Operational helpers, repo guards, inspection commands, and publish helpers.
- `tests/`
  Repo layout, schema, registry, API, and viewer tests.
- `fixtures/`
  Minimal public sample fixtures only.

## Public Vs Private

- Public repo: code, docs, tests, schemas, configs, small fixtures.
- Private workspace: source workbooks, raw imports, runtime releases, logs, and historical output trees.
- Runtime data for local dev and Render is expected to come from `production_data_processing`, not from tracked repo directories.

## Legacy And Transitional Areas

- Root-level `battery_7step_site/` has been retired from the public repo path.
- Root-level `output/`, `output_versions/`, and tracked `data/` trees are no longer part of the public repo contract.
- `trade_flow_opt_test` and the old writable repo copy now belong in the workspace archive area.
