# System Overview

## Three Layers

1. Public repository
   - Holds code, tests, schemas, configs, docs, and runbooks.
   - Defines how the app reads runtime bundles.

2. Private data workspace
   - Lives outside the repo.
   - Produces cleaned data, optimization diagnostics, and runtime bundle releases.
   - For this workspace family, `E:\zjl\CMU\research\website\production_data_processing` is the private processing lane.

3. Runtime bundle on Render
   - Holds only the minimum data needed for the website to run.
   - Exposed to the app through `RUNTIME_ROOT/current`.

## Request Flow

1. Browser loads `/`
2. Frontend requests `/api/bootstrap`
3. Frontend requests `/api/figure` or `/api/tables`
4. Web presenters call runtime facades
5. Runtime facades read the active bundle-compatible data layout
6. Response is returned as Sankey/table payloads

## Optimization Flow

1. Private workspace runs `conversion_factor_optimization`
2. Outputs are normalized into `first_optimization`
3. Publishing tools assemble a runtime bundle release
4. Bundle is validated and uploaded to Render storage
5. `current` is switched to the new release

## Why This Structure

- Keeps public code and private data separate
- Prevents the website from depending on ad hoc local folders
- Creates one formal product package instead of multiple parallel centers
- Makes future metal expansion explicit and predictable
