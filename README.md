# EV-Battery-Chemistry-Trade-Flow-Analysis

Deployment-ready repository for the current `trade_flow_opt` website and optimization pipelines.

Live website: [trade-flow-opt.onrender.com](https://trade-flow-opt.onrender.com/)

This repository is based on the previous paper
"Electric vehicle battery chemistry affects supply chain disruption vulnerabilities"
([Nature Communications](https://www.nature.com/articles/s41467-024-46418-1))
and the earlier GitHub repository
[acheng98/ev-battery-chemistry-supply-chain-vulnerabilities](https://github.com/acheng98/ev-battery-chemistry-supply-chain-vulnerabilities).

This research is associated with [CMU VEG](https://www.cmu.edu/cit/veg/index.html).

## What This Repo Contains

- `battery_7step_site/`
  The live FastAPI website used to render the precomputed 7-step Sankey diagrams.
- `src/trade_flow_opt/`
  The optimization pipelines and precomputation scripts.
- `tests/`
  Regression tests for the pipelines and web viewer.

## What This Repo Does Not Need To Expose

The website can stay fully functional without committing raw or precomputed data into the public repo.

Recommended separation:

- GitHub repo: code only
- Server/private storage: precomputed outputs and dataset files

At runtime the website reads those private files through environment variables.

## Required Runtime Environment Variables

- `BATTERY_SITE_OUTPUT_DIR`
  Absolute path to the active precomputed output directory.
- `BATTERY_SITE_OUTPUT_VERSIONS_DIR`
  Absolute path to the root folder that contains `v3/output`, `v4/output`, etc.
- `BATTERY_SITE_DATA_ROOT`
  Absolute path to the private dataset root that contains:
  - `ListOfreference.xlsx`
  - `production/country`
  - `trade/import`

## Optional Runtime Environment Variables

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
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -m uvicorn --app-dir E:\zjl\CMU\research\website\trade_flow_opt battery_7step_site.main:app --host 127.0.0.1 --port 8147
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

- Do not commit `output/`, `output_versions/`, `instance/`, or local log files.
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
   - `BATTERY_SITE_DATA_ROOT=/var/data/trade-flow-opt/data`
   - `BATTERY_SITE_OUTPUT_DIR=/var/data/trade-flow-opt/output`
   - `BATTERY_SITE_OUTPUT_VERSIONS_DIR=/var/data/trade-flow-opt/output_versions`
   - `BATTERY_SITE_INSTANCE_DIR=/var/data/trade-flow-opt/instance`
   - `BATTERY_SITE_ANALYST_PASSWORD=<your password>`
5. Optionally enable `BATTERY_SITE_STRICT_STARTUP=true` after the private data is in place.

## Suggested Render Start Command

```text
uvicorn --app-dir . battery_7step_site.main:app --host 0.0.0.0 --port $PORT
```
