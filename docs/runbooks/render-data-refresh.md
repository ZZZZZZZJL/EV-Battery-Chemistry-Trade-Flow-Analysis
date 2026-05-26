# Render Data Refresh

## Purpose

Refresh the private runtime bundle mounted on Render without committing private
data into the public GitHub repository. This is required whenever the online app
has current front-end code but stale or incomplete Sankey, optimization, or
Coefficient Explorer data.

## Standard Flow

1. In the private workspace, regenerate the baseline, optimization, and
   vulnerability-supporting runtime outputs.
2. Build or assemble one complete runtime release folder.
3. Validate the release locally.
4. Upload the release folder to the Render persistent disk.
5. Switch `/var/data/runtime/current` to the new release.
6. Restart or redeploy the Render service.
7. Run smoke checks and record the `data_release_id`.

## Bundle Naming

- Recommended: `data-YYYY-MM-DD-01`
- Same-day retries increment the numeric suffix, for example
  `data-2026-05-26-02`.

## Expected Render Layout

The Render service should use `RUNTIME_ROOT=/var/data/runtime`.

```text
/var/data/runtime/
|-- releases/
|   |-- data-YYYY-MM-DD-01/
|   |   |-- manifest.json
|   |   |-- catalog.json
|   |   |-- app_data/
|   |   |   |-- original/
|   |   |   |-- first_optimization/
|   |   |   |-- pareto_optimal/
|   |   |   |-- sn_minimum/
|   |   |   |-- deviation_minimum/
|   |   |   `-- reference/
|   |   `-- output_versions/
|   `-- previous-release/
|-- current
`-- previous
```

`current` and `previous` can be symbolic links when the Render shell supports
them. If symlinks are awkward on the service, keep a real `current/` directory
and replace it only after the new release passes validation.

## Required Runtime Contents

The app can render the VI dashboard from tracked static JS, but these runtime
files are still needed for Sankey, Analysis, and Coefficient Explorer features:

- Original snapshots under `app_data/original/`.
- Optimization snapshots under `app_data/pareto_optimal/`,
  `app_data/sn_minimum/`, and `app_data/deviation_minimum/`.
- Reference workbook under `app_data/reference/` or the configured
  `BATTERY_SITE_DATA_ROOT`.
- Optimizer diagnostics for each optimization result, especially either:
  - `intermediate/*coefficients*.csv`, or
  - `selected_stage_hyperparameters.csv` with workbook paths that are readable
    from the Render service.
- Flow comparison or transition-detail files if Trade Flow Explorer should be
  populated.

If coefficient diagnostics are missing, the front end will render the Analysis
section but Coefficient Explorer will report that no coefficient rows are present
in the active runtime data.

## Local Validation Before Upload

From the public repo root, point the app at the candidate release and inspect the
runtime status:

```powershell
$env:RUNTIME_ROOT='E:\path\to\runtime'
$env:BATTERY_SITE_APP_DATA_DIR='E:\path\to\runtime\current\app_data'
$env:BATTERY_SITE_OUTPUT_VERSIONS_DIR='E:\path\to\runtime\current\output_versions'
$env:BATTERY_SITE_DATA_ROOT='E:\path\to\runtime\current\app_data\reference'
E:\zjl\CMU\research\EVSupplyChain\website\.venv\Scripts\python.exe -B scripts\validate_runtime.py
```

Validate the bundle contract:

```powershell
E:\zjl\CMU\research\EVSupplyChain\website\.venv\Scripts\python.exe -B scripts\inspect_bundle.py E:\path\to\runtime\releases\data-YYYY-MM-DD-01
```

Then run the app locally against that release and check one known optimization
case in analyst mode. Confirm that `tables.producerCoefficients` is non-empty for
an optimization result that should expose coefficient rows.

## Upload Procedure

1. Open the Render Dashboard and confirm the service has a persistent disk
   mounted at `/var/data/runtime`.
2. Open the service Shell, or connect with SSH/SCP if SSH is configured.
3. Upload the prepared release folder to:

```text
/var/data/runtime/releases/<release-id>
```

4. Keep the previous release untouched.
5. Switch the active release:

```bash
cd /var/data/runtime
mv current previous-manual-backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
ln -s releases/<release-id> current
```

If symlinks are not available, replace the `current` directory after making a
backup:

```bash
cd /var/data/runtime
mv current previous-manual-backup-$(date +%Y%m%d-%H%M%S)
cp -a releases/<release-id> current
```

6. Restart the service from the Render Dashboard. Use **Clear build cache &
   deploy** only when static assets or dependency/build behavior look stale.

## Environment Variables

The Render service should include:

```text
APP_ENV=prod
RUNTIME_ROOT=/var/data/runtime
BATTERY_SITE_ANALYST_PASSWORD=<secret>
BATTERY_SITE_STRICT_STARTUP=true
```

If the bundle does not use the default `current/app_data` and
`current/output_versions` layout, also set:

```text
BATTERY_SITE_APP_DATA_DIR=/var/data/runtime/current/app_data
BATTERY_SITE_OUTPUT_VERSIONS_DIR=/var/data/runtime/current/output_versions
BATTERY_SITE_DATA_ROOT=/var/data/runtime/current/app_data/reference
```

## Smoke Test After Switch

Open these URLs:

- `/healthz`
- `/api/bootstrap`
- `/?metal=Ni&year=2024&result=baseline&theme=light&ref=1000000&s7=country`
- `/?metal=Ni&year=2024&result=pareto_optimal&theme=light&ref=1000000&s7=country#data-board`
- `/?metal=Ni&year=2024&result=pareto_optimal&theme=light&ref=1000000&s7=country#vulnerability-board`

For Analysis, use non-guest mode and verify that Coefficient Explorer has rows.
For VI, verify that Time Trend shows Original, Multiobjective, SN Minimum, and
Deviation Minimum in the legend.

## Rollback

If smoke tests fail:

1. Restore `current` to the previous known-good release.
2. Restart the Render service.
3. Rerun smoke checks.
4. Record the failed release id and stop rollout until the runtime bundle is
   rebuilt or repaired.
