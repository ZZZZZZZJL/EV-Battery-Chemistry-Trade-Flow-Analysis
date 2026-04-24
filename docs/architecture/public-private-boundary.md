# Public / Private Boundary

## Allowed In GitHub

- FastAPI app code
- baseline and optimization source code
- schemas and configs
- tests
- docs and runbooks
- minimal public fixtures and examples

## Not Allowed In GitHub

- private raw production workbooks
- private raw trade imports
- private intermediate spreadsheets
- private optimization diagnostics that expose production data
- runtime release bundles
- persistent-disk contents from Render
- local secrets or `.env` files
- legacy output trees kept only for historical comparison

## Workspace Interpretation

- `E:\zjl\CMU\research\website\EV-Battery-Chemistry-Trade-Flow-Analysis` is public.
- `E:\zjl\CMU\research\website\production_data_processing` is private.
- `RUNTIME_ROOT` on Render is private.
- The public repo no longer treats tracked `data/`, `output/`, or `output_versions/` directories as part of the supported runtime model.

## Contract Rule

The public repo may define:

- path conventions
- schemas
- validation logic
- publishing commands
- upload, switch, smoke-test, and rollback procedures

The public repo may not contain:

- long-lived private source datasets
- long-lived runtime release contents
- Render disk snapshots
