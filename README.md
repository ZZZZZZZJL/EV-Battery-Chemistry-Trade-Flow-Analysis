# Material Flow Studio

A local, public Flask workspace for configuring and generating EV battery
critical-mineral Sankey diagrams. It wraps the established
`manual_sankey_new` calculation and Plotly rendering pipeline instead of
reimplementing material-balance logic in the browser.
The online version is here: https://ev-battery-chemistry-trade-flow-analysis.onrender.com/

## What the website supports

- Li, Co, Ni, and Mn; trade years are discovered from local
  `UNComtrade_<year>_Import_ByPartner` folders.
- Complete chain: Mining → Processing → Refining → PCAM → Cathode → Battery.
- Optional Processing/Refining merge, PCAM removal, and Battery removal.
- Production-weighted or trade-balance node sizing.
- A separate production source for every active production stage.
- Multiple production statuses summed without probability weighting.
- Any number of HS code / conversion-factor rows for every post-trade step.
- Country, chemistry, or country + chemistry terminal nodes.
- Full country-name or ISO3 labels (hover and audit data retain full names).
- Single-result and A/B comparison modes with independent artifacts.
- A collapsible Setup rail for full-width comparison viewing.
- Flow and node transparency thresholds that do not change material balances,
  plus an always-keep country list and protection for gray special nodes.
- Dynamic Sankey height from the canonical renderer; the website does not
  force a fixed iframe height.
- PNG, self-contained HTML, manifest, conversion-factor, balance, stage-flow,
  and production-source audit downloads.

There is no private area, password, or analyst mode.

## Production data lifecycle

The repository bundles and always exposes these public workbooks:

- `USGS_production_data.xlsx`
- `ma_2026_production_data.xlsx`

SCInsight and Benchmark must be uploaded from the Production Library. Uploads
are assigned to a random ID stored in browser `sessionStorage`. A new browser
tab gets a new ID and cannot see uploads from another tab, so the workbook must
be uploaded again. Uploaded files are not copied into either source data
directory.

## Bundled public data

The repository is self-contained for its public data path:

- Import-by-partner trade folders for every year from 2018 through 2024.
- `data/production/USGS_production_data.xlsx`.
- `data/production/ma_2026_production_data.xlsx`.
- `data/reference/ListOfreference.xlsx` for country names, regions, and colors.

The default application settings read these files directly from `data/`; no
machine-specific `E:` drive path is required.

Every workbook is validated before it becomes selectable. The validator checks
the `<metal>_<stage>` sheet convention, required `id`, `reporterDesc`, and
`status` columns, available years, and status values. `Product` is required for
Cathode and Battery sheets, where chemistry allocation needs it; non-terminal
production sheets do not require that column. The UI then disables
stage/source combinations that do not cover the selected metal, stage, and
year.

## Comparison behavior

Choose **Compare** above the result area, then select **A** or **B** beside the
Generate button. Only the selected slot is regenerated. The other slot and the
last successful result in the selected slot remain available if generation
fails, so route, source, label, or factor changes can be compared safely.
After a slot has generated successfully, selecting A or B restores the complete
setup used for that slot, including sources, HS factors, statuses, display
options, thresholds, and preserved countries. **Hide setup** expands the result
workspace without discarding either scenario.

Visibility thresholds operate after material-flow calculation. A flow or
regular node below its threshold becomes transparent but remains in the Plotly
layout and all audit outputs. Flows and nodes involving an always-kept country
remain visible, and gray unknown/non-producer special nodes are never hidden by
the node threshold.

Metal presets are matched to the active source/target stage pair rather than a
fixed step number. Newly exposed pairs receive their metal default; manually
edited pairs are preserved while folding and reopening the chain until the
user explicitly reapplies the preset or changes metal.

## Run locally

From this folder:

```powershell
D:\Python\anaconda3\python.exe -m pip install -r requirements.txt
D:\Python\anaconda3\python.exe app.py
```

Open <http://127.0.0.1:5050>.

The repository-relative defaults can be overridden with environment variables:

- `SANKEY_DATA_ROOT`
- `MANUAL_SANKEY_CORE_ROOT`
- `SANKEY_TRADE_ROOT`
- `SANKEY_REFERENCE_FILE`

## Architecture

```text
app.py                         Flask entrypoint
sankey_core/                   Canonical material-flow and Plotly renderer
sankey_web/
  settings.py                 Local path and source registry
  inventory.py                Workbook/schema/coverage inspection
  generation.py               Web request → manual_sankey_new adapter
  web.py                      Public API, uploads, artifacts
  templates/index.html        Operational workspace
  static/css/app.css          Restrained responsive design system
  static/js/app.js            Client state and interactions
tests/test_web.py             Inventory, route, session, upload tests
data/
  UNComtrade_2018_Import_ByPartner/
  ...
  UNComtrade_2024_Import_ByPartner/
  production/                 Bundled USGS and Ma et al., 2026 workbooks
  reference/                  Country-name, region, and color workbook
.runtime/
  uploads/<session-hash>/     Ephemeral uploaded workbooks
  artifacts/<session-hash>/   Generated PNG/HTML/audit bundles
```

The browser never reads production or trade files directly. The backend passes
a validated scenario into the bundled `sankey_core` pipeline
and `run_pipeline()`. This keeps importer/exporter handling, producer-only
production constraints, chemistry allocation, balances, reference sizing, and
dynamic height identical to the current local exporter.

## Tests

```powershell
D:\Python\anaconda3\python.exe -m unittest discover -s tests -v
node --check sankey_web\static\js\app.js
```
