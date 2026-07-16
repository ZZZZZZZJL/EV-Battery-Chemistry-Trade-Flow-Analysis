# Standalone Custom Sankey

This folder generates a Sankey PNG and standalone HTML directly from:

- either the Benchmark or SCInsight country production workbooks;
- annual `UNComtrade_<year>_Import_ByPartner` folders;
- the runtime `ListOfreference.xlsx` country names, regions, and colors.

It does not start or modify the web application. The node layout, link opacity, fonts, reference node, sorting, and spacing follow the existing website implementation. PNG width is configured by `IMAGE_WIDTH`; height is calculated dynamically from the material scale and content so the reference node keeps the same pixel height across runs.

Exported PNG files use a white background. Set `LABEL_FONT_SIZE` in the configuration to change country/node labels, production/post-trade stage titles, and the reference-quantity label together.

## 1. Edit `config.py`

Set the metal, year, route, production source, cathode view, HS codes, conversion factors, and output root.

The preferred route configuration is dynamic:

```python
MERGE_PROCESSING_REFINING = False
SHOW_PCAM = True
SHOW_BATTERY = True
```

The default chain is mining -> processing -> refining -> pcam -> cathode ->
battery, with a Post Trade stage between each pair. Merging uses the `pro_ref`
workbook and labels it Intermediate. Hiding PCAM connects Refining -> Post Trade
-> Cathode. Hiding Battery stops the flow at Cathode. Every required workbook
must exist; for example Li with `SHOW_PCAM=True` reports the missing
`lithium_pcam.xlsx` rather than silently bypassing it.

Node detail is configured independently:

```python
NODE_VIEW = "country_chemistry"  # country / chemistry_only / country_chemistry
CHEMISTRY_STAGE_SCOPE = "both"   # both / battery_only
MERGE_LMFP_INTO_LFP = True
```

`battery_only` keeps Cathode at country level and splits only Battery. With
`both`, Cathode and Battery are both split. When LMFP is not merged, its
Cathode contained-mineral flow enters Battery as `OTHER` because the current
Battery workbooks do not report LMFP.

If the same HS code is configured in adjacent transitions, its raw bilateral
records are used once:

```python
SHARED_HS_TRADE_OWNER = "downstream"  # or upstream
```

Chemistry-specific factors can replace the single HS factor with a production-
share-weighted coefficient. For example, 50% LFP at 0.2 and 50% NCA at 0.4
produces an effective pre-cap factor of 0.3:

```python
CHEMISTRY_CONVERSION_FACTORS = {
    "LFP": 0.20,
    "LMFP": 0.20,
    "NMC": 0.40,
    "NCA": 0.40,
}
```

After conversion, country matching uses only contained mineral; source and
destination chemistry do not have to match. The conversion audit records the
configured factor, weighted factor, factor basis, chemistry shares, production
cap multiplier, and final effective factor.

Choose a production source independently for every active production stage:

```python
PRODUCTION_SOURCE_BY_STAGE = {
    "mining": "usgs",
    "processing": "scinsight",
    "refining": "scinsight",
    "pro_ref": "scinsight",
    "pcam": "scinsight",
    "cathode": "benchmark",
    "battery": "scinsight",
}
```

`PRODUCTION_ROOTS` maps `usgs`, `scinsight`, `ma_2026`, and `benchmark` to the
four consolidated `.xlsx` workbooks. Each workbook contains one sheet per
available metal/stage, such as `nickel_mining`. Only active route stages are
required. A missing source mapping, workbook, or metal/stage sheet stops the
run and reports the source, stage, expected sheet, and available sheets; no
fallback source is used. `PRODUCTION_SOURCE` remains only as a backward-
compatible fallback when `PRODUCTION_SOURCE_BY_STAGE` is absent.

Choose the production statuses once for SCInsight/Benchmark stages:

```python
PRODUCTION_SHEETS = "all"
# or, summed without probability weighting:
PRODUCTION_SHEETS = ["operating", "highly probable"]
```

The selected statuses are summed without probability weighting. USGS and MA
contain only `status=all`, so those stages automatically use `all` even when
the global selection requests operating/probable for other sources. When a
subset is selected, every output filename includes a normalized suffix such as
`_operating-highly_probable`. A missing requested status stops the run and
reports the source, stage, requested statuses, and available statuses.

Set the node-size mode:

```python
USE_PRODUCTION_DATA = True   # production quantities determine node sizes
USE_PRODUCTION_DATA = False  # trade-only material-flow balance determines node sizes
LABEL_FONT_SIZE = 12
```

In trade-only mode, production workbooks are still required but their quantities are used only to identify selected-year positive-production country lists and calculate cathode chemistry shares. Production-cap scaling is disabled, so the effective conversion factor equals the manual conversion factor.

Supported routes:

| `ROUTE` | Production chain |
| --- | --- |
| `full` | mining -> post trade -> processing -> post trade -> refining -> post trade -> cathode |
| `intermediate` | mining -> post trade -> pro_ref -> post trade -> cathode |
| `completed` | mining -> post trade -> processing -> post trade -> refining -> post trade -> pcam -> post trade -> cathode |

`full` uses `post_trade_1` through `post_trade_3`, `intermediate` uses `post_trade_1` through `post_trade_2`, and `completed` uses `post_trade_1` through `post_trade_4`. The old names `pro_ref` and `pcam` remain accepted as aliases but outputs always use the canonical names. Remove unrelated keys from `POST_TRADE_HS` when changing routes; unknown step names are rejected to prevent a silent configuration error.

The selected metal must have every required workbook. A missing stage fails immediately with a message containing the missing file path. The tool does not synthesize missing `pro_ref` or `pcam` data.

Supported cathode views:

| `CATHODE_VIEW` | Cathode nodes |
| --- | --- |
| `country` | One `Product=Total` node per country |
| `chemistry` or `chemistry_only` | Global chemistry nodes |
| `country_chemistry` | One country/chemistry node per combination |

Enter HS codes as strings:

```python
POST_TRADE_HS = {
    "post_trade_1": {"260400": 0.55},
    "post_trade_2": {"750110": 0.80, "750120": 0.55},
    "post_trade_3": {},  # no trade data; balance still runs with imports/exports = 0
}
```

For Li, HS codes in the final trade step can identify the lithium salt feeding
the cathode-chemistry allocation:

```python
POST_TRADE_PRODUCTS = {
    "post_trade_3": {
        "282520": "Lithium Hydroxide",
        "283691": "Lithium Carbonate",
    },
}
```

Lithium Carbonate preferentially feeds LFP/LMFP and Lithium Hydroxide
preferentially feeds NMC/NCA. Non-preferred routes retain a 0.25 affinity so a
country such as Australia, whose production table contains LFP but whose trade
input is hydroxide, remains representable. Allocation within the resulting
chemistry set follows that country's selected-sheet cathode production shares.
The lithium-salt Product rows are a parallel classification and are excluded
from the battery-chemistry sum, preventing double counting against Product=Total.

The `1.0` coefficients in the bundled example are placeholders for a runnable software check. Replace them with the intended coefficients before using the image analytically.

## 2. Run

Select a Python 3.11+ interpreter in VS Code or PyCharm and install this folder's requirements if needed:

```powershell
python -m pip install -r requirements.txt
python run.py
```

You can keep multiple cases without editing the bundled file:

```powershell
python run.py --config E:\path\to\my_case.py
```

The custom configuration file must expose the same setting names as `config.py`.

## Trade direction and conversion rules

The raw files are import data:

- the reporter/file-name prefix is the importer;
- `partnerCode` is the exporter;
- `partnerCode=0` is the World aggregate and is excluded;
- `qty` is converted from kg to tonnes, with `netWgt / 1000` as the fallback.

For each bilateral flow:

```text
converted_before_scaling = raw_tonnes * manual_factor

producer_multiplier = min(
    1,
    exporter_stage_production / exporter_total_converted_trade
)

effective_factor = manual_factor * producer_multiplier
final_trade = raw_tonnes * effective_factor
```

The production multiplier is applied only when the exporter exists in the upstream production workbook with production greater than zero. Non-source exporters keep the manual factor, matching the website's special-node treatment.

In trade-only mode the multiplier is always `1`. For each country, consecutive production-stage membership is solved as one material-balance segment. Downstream deficits propagate upstream and upstream surpluses propagate downstream. If propagation reaches a stage where the country is absent from the adjacent production list, the remaining amount becomes Unknown Source or Unknown Destination. Mining is the open chain source and cathode is the terminal sink.

Countries that belong to a production-stage list but have zero inferred material flow remain in the stage audit with `node_size=0`; Plotly omits them from the rendered image because a zero-height Sankey node is not visible.

Trade is classified as:

- producer -> producer: included as a bilateral flow;
- producer -> no downstream production: included through the Non-Target special node;
- no upstream production -> producer: included through the From Non-Source special node;
- no upstream production -> no downstream production: excluded from the Sankey and retained in the conversion-factor audit.

Unused upstream production becomes same-country domestic flow when that country has downstream production. Otherwise it goes to the Non-Target node. Downstream shortages become Unknown Source; excess incoming material goes to Unknown Destination.

Production rows with no country `id` are ignored and listed in the ignored-production audit.

## Outputs

Every invocation creates a new timestamped folder below `OUTPUT_ROOT`. For a
single-source Benchmark Ni 2024 full run, its shape is:

- `outputs\Ni_2024_full_benchmark_<timestamp>\Ni_2024_full_benchmark.png`
- `outputs\Ni_2024_full_benchmark_<timestamp>\Ni_2024_full_benchmark.html`
- the same prefix followed by `_conversion_factors.csv`, `_balance_audit.csv`,
  `_ignored_production_rows.csv`, `_stage_material_flow.csv`,
  `_production_sheet_summary.csv`, and `_manifest.json`

Thus every filename identifies the metal, year, canonical route, and production
source. A mixed-source run includes an ordered stage/source signature such as
`mining-usgs_processing-scinsight_..._cathode-benchmark`. The manifest and
`_production_sheet_summary.csv` record the exact source workbook, metal/stage
sheet, and statuses used for every stage. The HTML is self-contained and can be
opened directly in a browser.

The conversion table records importer/exporter direction, raw tonnes, manual coefficient, exporter production, production multiplier, effective coefficient, final trade quantity, classification, inclusion status, and source file.

The stage material-flow table records trade imports/exports, upstream/downstream domestic flow, Unknown Source/Destination, inferred node size, and the final material-balance residual for every production country and stage. It is populated in trade-only mode.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests cover route lengths, importer/exporter direction, World-row filtering, producer-only scaling, Non-Source behavior, ignored no-source/no-target trade, zero-trade balance, chemistry nodes, missing-stage errors, and dynamic rendering.
