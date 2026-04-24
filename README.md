# EV-Battery-Chemistry-Trade-Flow-Analysis

Public repository for the EV battery chemistry trade-flow web product, the baseline analysis pipeline, and the first-generation `conversion_factor_optimization` engine.

Live website: [trade-flow-opt.onrender.com](https://trade-flow-opt.onrender.com/)

## Research Context

This research is associated with the [CMU Vehicle Electrification Group](https://www.cmu.edu/cit/veg/) and builds on the Nature Communications article [Electric vehicle battery chemistry affects supply chain disruption vulnerabilities](https://www.nature.com/articles/s41467-024-46418-1). It also follows from the earlier public repository [acheng98/ev-battery-chemistry-supply-chain-vulnerabilities](https://github.com/acheng98/ev-battery-chemistry-supply-chain-vulnerabilities).

## Repository Model

This repository follows four hard rules.

1. `src/trade_flow/` is the only formal product package.
2. `apps/web/app.py` is the only public ASGI entrypoint.
3. Runtime data is read from a private runtime bundle, not from tracked repo data folders.
4. Private production-data processing stays in `E:\zjl\CMU\research\website\production_data_processing`.

`src/trade_flow/legacy_site/` still exists as a temporary internal compatibility namespace for code that has not been fully re-homed yet. It is not a second product center and should shrink over time.

## Key Directories

- `apps/web/`: public app entrypoint
- `src/trade_flow/web/`: canonical web package, routes, presenters, templates, static assets
- `src/trade_flow/domain/`: runtime path contracts, manifest models, validation helpers
- `src/trade_flow/runtime/`: runtime bundle loader, dataset registry, repository facade
- `src/trade_flow/baseline/`: baseline analysis logic
- `src/trade_flow/conversion_factor_optimization/`: official first-generation optimization engine
- `src/trade_flow/optimization/`: stable optimization-facing facades and shared helpers
- `src/trade_flow/metals/`: metal adapter registry and per-metal extension points
- `src/trade_flow/pipelines/`: high-level baseline and first-optimization pipeline facades
- `src/trade_flow/publishing/`: runtime bundle build, validation, and first-optimization publishing helpers
- `configs/`, `schemas/`, `docs/`, `scripts/`, `tests/`, `fixtures/`: repo contracts, docs, tools, checks, and minimal public examples

## Runtime Environment Variables

- `APP_ENV`: deployment profile, usually `dev` or `prod`
- `RUNTIME_ROOT`: private runtime root that contains `releases/`, `current/`, and `previous/`
- `BATTERY_SITE_APP_DATA_DIR`: optional explicit app-data root
- `BATTERY_SITE_OUTPUT_VERSIONS_DIR`: optional explicit output-snapshot root
- `BATTERY_SITE_DATA_ROOT`: optional explicit shared/reference data root
- `BATTERY_SITE_REFERENCE_FILE`: optional explicit reference workbook override
- `BATTERY_SITE_INSTANCE_DIR`: writable local instance directory
- `BATTERY_SITE_ANALYST_PASSWORD`: analyst-mode password
- `BATTERY_SITE_STRICT_STARTUP`: if `true`, fail startup when runtime files are incomplete

## Local Development

```powershell
$env:PYTHONPATH='src;.'
$env:BATTERY_SITE_APP_DATA_DIR='E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current\app_data'
$env:BATTERY_SITE_OUTPUT_VERSIONS_DIR='E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current\output_versions'
$env:BATTERY_SITE_DATA_ROOT='E:\zjl\CMU\research\website\production_data_processing\source_private\shared'
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -m uvicorn --app-dir . apps.web.app:app --host 127.0.0.1 --port 8147
```

## Verification

```powershell
$env:PYTHONPATH='src;.'
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -B scripts\validate_repo.py
```

```powershell
$env:PYTHONPATH='src;.'
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

```powershell
$env:PYTHONPATH='src;.'
$env:BATTERY_SITE_APP_DATA_DIR='E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current\app_data'
$env:BATTERY_SITE_OUTPUT_VERSIONS_DIR='E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current\output_versions'
$env:BATTERY_SITE_DATA_ROOT='E:\zjl\CMU\research\website\production_data_processing\source_private\shared'
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -B scripts\smoke_test_app.py
```

## Architecture And Runbooks

- `docs/architecture/repo-layout-and-file-responsibilities.md`
- `docs/architecture/system-overview.md`
- `docs/architecture/public-private-boundary.md`
- `docs/architecture/metal-extension-model.md`
- `docs/architecture/runtime-bundle-spec.md`
- `docs/architecture/monorepo-refactor-blueprint.md`
- `docs/runbooks/render-deploy.md`
- `docs/runbooks/render-data-refresh.md`
- `docs/runbooks/emergency-rollback.md`
