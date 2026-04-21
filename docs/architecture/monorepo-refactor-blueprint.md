# Workspace Final-State Blueprint

## Target Workspace Layout

```text
E:\zjl\CMU\research\website
|-- .venv/
|-- EV-Battery-Chemistry-Trade-Flow-Analysis/
|-- worktrees/
|   `-- EV-Battery-Chemistry-Trade-Flow-Analysis/
|       |-- arch-repo-governance/
|       |-- web-product/
|       |-- flow-first-optimization/
|       `-- release-v1.0.0/
|-- production_data_processing/
|   |-- source_private/
|   |-- pipelines/
|   |   `-- metal_processing/
|   |-- runtime_releases/
|   |-- manifests/
|   `-- logs/
|-- archive/
`-- README_workspace.md
```

## Operating Model

1. `EV-Battery-Chemistry-Trade-Flow-Analysis/` is the only official public repository path.
2. Linked worktrees live under `worktrees/EV-Battery-Chemistry-Trade-Flow-Analysis/` instead of the workspace root.
3. `production_data_processing/` is the private processing and runtime-release area.
4. `archive/` holds old working copies, retired experiments, and legacy output trees.

## Public Repository Rules

- `src/trade_flow/` is the single formal package.
- `apps/web/app.py` is the single formal ASGI entrypoint.
- `conversion_factor_optimization` is the only official first-generation optimization engine.
- `first_optimization` is the only official published optimization result name.
- Large raw trade data, private workbooks, runtime releases, and historical output trees do not stay in the public repo.

## Private Workspace Rules

- `source_private/` keeps private workbook inputs and raw trade data.
- `pipelines/metal_processing/` keeps mirrored private-processing scripts.
- `runtime_releases/releases/<release-id>/` stores the active publishable runtime artifacts.
- `runtime_releases/current` points to the active runtime release.
- `manifests/` records private release metadata.

## Sync Rules

- Code changes are committed from the official public repo path.
- Branch-specific work happens inside linked worktrees.
- Private data refreshes are built in `production_data_processing/` and then exposed to the app through runtime env vars.
- Legacy directories should be archived before deletion when they might still contain useful history.
