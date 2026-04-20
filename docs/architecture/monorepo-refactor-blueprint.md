# Monorepo Blueprint

## Objective

This repository is now the first clean product version of the project. Its structure separates:

- web delivery
- baseline trade-flow computation
- conversion-factor optimization
- publishing and runtime snapshot generation
- private production data and deployment-only assets

## Product Model

The repository is managed as one product with two tightly connected systems:

1. Web Product
   The FastAPI site, APIs, templates, runtime validation, and Render deployment surface.
2. Computation Product
   The baseline pipeline and the `conversion_factor_optimization` engine that generate assets for the website.

## Current Structure

```text
apps/
  web/                              # Canonical ASGI entrypoint

battery_7step_site/                 # Active website package

src/
  trade_flow/
    baseline/                       # Baseline export and graph logic
    common/                         # Shared paths and helpers
    contracts/                      # Runtime snapshot contracts
    conversion_factor_optimization/ # Conversion-factor optimization engine
    publishing/                     # First Optimization sync and runtime publishing
    runtime/                        # Runtime readers and validators

scripts/
  release/                          # Release and validation commands

tests/                              # Regression coverage
docs/                               # Architecture and runbooks

data/                               # Private runtime data
instance/                           # Private writable runtime state
output/                             # Local exported outputs
output_versions/                    # Private published snapshots
```

## Directory Responsibilities

### `apps/web/`

- The only supported web entrypoint is `apps.web.app:app`.
- Render and local development must both use this path.

### `battery_7step_site/`

- Owns the active website code: routes, templates, static assets, and runtime services.
- User-facing web behavior belongs here unless it is shared business logic.

### `src/trade_flow/baseline/`

- Owns the current baseline computation logic.
- Must stay independent from presentation concerns.

### `src/trade_flow/conversion_factor_optimization/`

- Owns the iterative optimization engine and HS-role rules.
- All future conversion-factor work lands here.

### `src/trade_flow/publishing/`

- Converts optimizer outputs into First Optimization runtime assets.
- Owns repeatable release and synchronization behavior.

### `src/trade_flow/runtime/`

- Reads runtime payloads, validates completeness, and supports the website.

### `src/trade_flow/contracts/`

- Defines shared contracts between computation, publishing, and site runtime.

### `scripts/release/`

- Exposes operational commands for optimization, publishing, and validation.

## Public vs Private Boundary

### Safe for GitHub

- application code
- pipeline code
- tests
- docs
- schemas and contracts
- deployment configuration

### Private and Render-only

- production data
- raw import datasets
- optimizer diagnostics
- generated runtime outputs
- historical release payloads
- analyst secrets and passwords

The current data restriction is `production data`, so those assets stay on private storage mounted into Render rather than in GitHub.

## Deployment Policy

Production should always follow this model:

- code from GitHub
- private runtime assets from mounted storage
- startup via `apps.web.app:app`

Required discipline:

- deployment cannot depend on sibling folders outside the repository
- runtime validation must fail loudly when private data wiring is broken
- release scripts must be rerunnable and deterministic

## Management Rules

- every release is scriptable
- every runtime dependency is documented
- every private path is environment-driven
- every cross-system data handoff has a named contract

## Success Criteria

The structure is successful when:

- one repository contains the full product lifecycle
- optimizer iteration has one canonical home
- GitHub contains only safe-to-share assets
- Render receives only private runtime payloads
- new contributors can understand where code belongs without tribal knowledge
