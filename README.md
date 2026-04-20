# EV-Battery-Chemistry-Trade-Flow-Analysis

Deployment-ready monorepo for the current EV battery trade-flow web product, baseline pipelines, and the `conversion_factor_optimization` engine.

Live website: [trade-flow-opt.onrender.com](https://trade-flow-opt.onrender.com/)

This repository is based on the previous paper
"Electric vehicle battery chemistry affects supply chain disruption vulnerabilities"
([Nature Communications](https://www.nature.com/articles/s41467-024-46418-1))
and the earlier GitHub repository
[acheng98/ev-battery-chemistry-supply-chain-vulnerabilities](https://github.com/acheng98/ev-battery-chemistry-supply-chain-vulnerabilities).

This research is associated with [CMU VEG](https://www.cmu.edu/cit/veg/index.html).

## What This Repo Contains

- `apps/web/`
  Canonical web application entrypoint for the FastAPI product surface.
- `battery_7step_site/`
  Active website package containing routes, templates, static assets, and runtime services.
- `src/trade_flow/`
  Canonical monorepo package containing `baseline`, `conversion_factor_optimization`, `publishing`, `runtime`, and `contracts`.
- `scripts/release/`
  Canonical release entrypoints for runtime snapshot validation and conversion-factor optimization.
- `tests/`
  Regression tests for the pipelines and web viewer.

## Architecture Blueprint

The formal monorepo restructuring blueprint lives at:

- `docs/architecture/monorepo-refactor-blueprint.md`

## What This Repo Does Not Need To Expose

The website can stay fully functional without committing production data or precomputed runtime outputs into the public repo.

Recommended separation:

- GitHub repo: code, contracts, docs, and fixtures only
- Server/private storage: production data, raw imports, optimizer diagnostics, and runtime outputs

At runtime the website reads those private files through environment variables.

## Required Runtime Environment Variables

- `BATTERY_SITE_OUTPUT_VERSIONS_DIR`
  Absolute path to the root folder that contains published output snapshots.
- `BATTERY_SITE_DATA_ROOT`
  Absolute path to the private dataset root that contains:
  - `ListOfreference.xlsx`
  - `production/country`
  - `trade/import`

## Optional Runtime Environment Variables

- `BATTERY_SITE_APP_DATA_DIR`
  Absolute path to the app-local data layout root that contains `original/` and `first_optimization/`.
- `BATTERY_SITE_INSTANCE_DIR`
  Writable folder for local instance files and logs.
- `BATTERY_SITE_DATASET_CONFIG`
  Override JSON config path for dataset settings.
- `BATTERY_SITE_ANALYST_PASSWORD`
  Password for analyst mode. Defaults to `88888888` for local development only.
- `BATTERY_SITE_STRICT_STARTUP`
  If set to `1`/`true`, the app will refuse to start when required private data folders are missing.

## Local Development

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -m uvicorn --app-dir . apps.web.app:app --host 127.0.0.1 --port 8147
```

## Tests

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

## Runtime Validation

Use this before or after deployment to confirm the private runtime paths are wired correctly:

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe scripts/validate_runtime.py
```

The web service also exposes:

```text
/healthz
```

It returns `200` only when the required templates, static files, active outputs, versioned outputs, and private dataset paths are available.

## Deployment Notes

- Do not commit `data/`, `output/`, `output_versions/`, `instance/`, or local log files.
- Keep precomputed CSV / JSON / XLSX files in private server storage.
- The frontend only calls API endpoints; no raw data directory should be mounted as static files.
- Analyst mode password should be injected through `BATTERY_SITE_ANALYST_PASSWORD` in production.

## Suggested Render Setup

1. Create a Render Web Service from this repository.
2. Add a persistent disk mounted at a private path such as:
   - `/var/data/trade-flow-opt`
3. Populate the disk with:
   - `/var/data/trade-flow-opt/data`
   - `/var/data/trade-flow-opt/output`
   - `/var/data/trade-flow-opt/output_versions`
   - `/var/data/trade-flow-opt/instance`
4. Configure environment variables:
   - `BATTERY_SITE_APP_DATA_DIR=/var/data/trade-flow-opt/data`
   - `BATTERY_SITE_DATA_ROOT=/var/data/trade-flow-opt/data/shared`
   - `BATTERY_SITE_OUTPUT_VERSIONS_DIR=/var/data/trade-flow-opt/output_versions`
   - `BATTERY_SITE_INSTANCE_DIR=/var/data/trade-flow-opt/instance`
   - `BATTERY_SITE_ANALYST_PASSWORD=<your password>`
5. Optionally enable `BATTERY_SITE_STRICT_STARTUP=true` after the private data is in place.

## Suggested Render Start Command

```text
uvicorn --app-dir . apps.web.app:app --host 0.0.0.0 --port $PORT
```
