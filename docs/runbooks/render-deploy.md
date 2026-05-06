# Render Deploy

## Goal

Deploy public code from GitHub while mounting a private runtime bundle disk on Render.

## Code Source

- GitHub repository: this repo
- App entrypoint: `apps.web.app:app`
- Start command: `uvicorn --app-dir . apps.web.app:app --host 0.0.0.0 --port $PORT`

## Required Render Configuration

1. Create a Python web service from the GitHub repo.
2. Mount a persistent disk at `/var/data/runtime`.
3. Set environment variables:
   - `APP_ENV=prod`
   - `RUNTIME_ROOT=/var/data/runtime`
   - `BATTERY_SITE_ANALYST_PASSWORD=<secret>`
   - optionally `BATTERY_SITE_STRICT_STARTUP=true`

## First Deploy

1. Deploy code from GitHub.
2. Confirm the service starts.
3. Upload the first runtime bundle into `/var/data/runtime/releases/<release-id>`.
4. Point `/var/data/runtime/current` at the active release content.
5. Run smoke checks:
   - `/healthz`
   - `/api/bootstrap`
   - one known `/api/figure` call

## Code-Only Update

1. Merge code to GitHub.
2. Let Render redeploy.
3. Do not touch the bundle if schema and runtime contract did not change.
4. Run smoke checks.
5. For front-end interaction updates, also verify:
   - the initial page shell loads before the Sankey chart finishes rendering
   - selector changes show a chart loading overlay instead of a full-page refresh
   - fast metal/year/result switching does not let an older chart overwrite the latest selection
   - Advanced controls open smoothly and node position overrides only request the backend on Apply or Reset
   - guest mode still hides diagnostics and analyst mode still requires `BATTERY_SITE_ANALYST_PASSWORD`

## Data-Only Update

1. Build a new bundle in the private workspace.
2. Validate it locally.
3. Upload it to `/var/data/runtime/releases/<new-release-id>`.
4. Switch `current`.
5. Run smoke checks.

## If Bundle Is Missing

- `/healthz` should return non-200
- the service should stay diagnosable
- if `BATTERY_SITE_STRICT_STARTUP=true`, startup may intentionally fail
