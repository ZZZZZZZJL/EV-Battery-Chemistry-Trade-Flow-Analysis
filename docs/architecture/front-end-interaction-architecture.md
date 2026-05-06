# Front-End Interaction Architecture

## Goal

The web viewer uses the existing FastAPI, Jinja, vanilla JavaScript, Plotly, and CSS stack. The interaction layer is organized so common user actions do not trigger full-page refreshes or uncontrolled overlapping figure requests.

## State Flow

```text
user input -> app_state -> api_client -> figure_controller -> Plotly.react
```

- `app_state.js` owns URL-safe selection state: metal, year, result mode, cobalt mode, theme, reference quantity, and S7 display mode.
- `api_client.js` owns `/api/bootstrap` and `/api/figure` calls. It cancels stale figure requests with `AbortController`, coalesces identical in-flight requests, and caches repeat guest-mode figures in memory.
- `figure_controller.js` owns the Plotly lifecycle. It shows chart loading/error overlays, debounces resize work, and reuses the existing chart container with `Plotly.react`.
- `ui_shell.js` provides lightweight shared interaction helpers such as debounce, busy state, and inline status feedback.

## API Boundary

`/api/bootstrap` returns lightweight metadata only: available metals, years, modes, labels, defaults, and a public runtime manifest summary. It must not return Plotly figure JSON, flow tables, private file names, or server paths.

`/api/figure` returns the Plotly figure payload and public/authorized table payload for the selected state. It validates public parameters, verifies analyst mode before touching runtime data, uses a process-local cache keyed by public request parameters plus runtime cache version, and sanitizes missing-runtime errors.

## Private Data Boundary

The browser only sees public selection metadata and authorized figure/table payloads. It never receives private runtime roots, Render direct-file locations, local absolute paths, passwords, tokens, or raw production workbooks. Analyst mode still depends on the server-side `BATTERY_SITE_ANALYST_PASSWORD` environment variable.

## Local Smoke Test

```powershell
$env:PYTHONPATH='src;.'
$env:BATTERY_SITE_APP_DATA_DIR='E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current\app_data'
$env:BATTERY_SITE_OUTPUT_VERSIONS_DIR='E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current\output_versions'
$env:BATTERY_SITE_DATA_ROOT='E:\zjl\CMU\research\website\production_data_processing\source_private\shared'
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -m uvicorn --app-dir . apps.web.app:app --host 127.0.0.1 --port 8155
```

Manual checks:

- `/api/bootstrap` responds quickly and does not contain `figure` or `tables`.
- Changing metal/year/result shows a loading overlay and only the latest request updates the chart.
- Advanced controls open without a full page refresh.
- Guest mode cannot see diagnostics; analyst mode still requires the environment password.

## Render Verification

After deployment, verify `/healthz`, `/api/bootstrap`, and one known `/api/figure` request. Then test the browser actions above on the Render URL. Runtime data remains on the Render disk/direct-file bundle and is not committed to GitHub.

## Rollback

If the optimized interaction layer misbehaves, revert the code-only deploy to the previous GitHub commit. The private runtime bundle does not need to change. The public ASGI entrypoint remains `apps/web/app.py`, so Render rollback is a normal code redeploy.
