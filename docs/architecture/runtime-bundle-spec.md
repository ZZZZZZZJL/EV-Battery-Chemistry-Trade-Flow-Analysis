# Runtime Bundle Spec

## Active Bundle Roots

- Local private workspace: `E:\zjl\CMU\research\website\production_data_processing\runtime_releases\current`
- Render: `RUNTIME_ROOT/current`, typically `/var/data/runtime/current`

## Release Layout

```text
runtime/
|-- releases/
|   `-- data-YYYY-MM-DD-01/
|       |-- manifest.json
|       |-- catalog.json
|       |-- app_data/
|       |   |-- original/
|       |   |-- first_optimization/
|       |   `-- reference/
|       `-- output_versions/
|-- current
`-- previous
```

## Required Files

- `manifest.json`
  Release metadata: schema version, release id, built time, public code commit, private pipeline tag, algorithms, metals, years, hashes.
- `catalog.json`
  Relative directory map for app-compatible runtime layout.

## Required Manifest Fields

- `schema_version`
- `data_release_id`
- `built_at`
- `public_code_commit`
- `private_pipeline_tag`
- `algorithms`
- `metals`
- `years`
- `hashes`

## Compatibility Rule

The public app currently reads an app-compatible layout under `app_data/` so the viewer can stay stable while runtime publication is fully bundle-driven. Shared private reference data is allowed to live outside `app_data/` and be injected through `BATTERY_SITE_DATA_ROOT`.
