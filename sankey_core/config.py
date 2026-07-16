"""Edit this file, then run ``python run.py`` from this folder."""

import os
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("SANKEY_DATA_ROOT", str(REPOSITORY_ROOT / "data")))

# Main selections. Supported metals: Li, Co, Ni, Mn.
METAL = "Li"
YEAR = 2024

# full         : mining -> processing -> refining -> cathode
# intermediate : mining -> pro_ref -> cathode
# completed    : mining -> processing -> refining -> pcam -> cathode
ROUTE = "full"

# Dynamic production-chain controls. These take precedence over ROUTE.
# Default: mining -> processing -> refining -> pcam -> cathode -> battery.
MERGE_PROCESSING_REFINING = False
SHOW_PCAM = False
SHOW_BATTERY = True

# country           : one cathode node per country using Product=Total
# chemistry_only    : global cathode chemistry nodes
# country_chemistry : one cathode node per country and chemistry
NODE_VIEW = "chemistry_only"

# Country node labels: "full" for the reference country name, or "iso3" for
# the ISO alpha-3 abbreviation. Hover text and audit tables retain full names.
COUNTRY_LABEL_MODE = "full"

# Optional visibility filters in tonnes. Values below the thresholds remain in
# the balance/layout but render transparently. Country ids listed here remain
# visible; gray special nodes are never hidden by the node threshold.
FLOW_TRANSPARENCY_THRESHOLD = 0
NODE_TRANSPARENCY_THRESHOLD = 0
PRESERVE_COUNTRY_IDS = []

# For chemistry_only/country_chemistry: split both Cathode and Battery, or keep
# Cathode as country and split only Battery.
CHEMISTRY_STAGE_SCOPE = "battery_only"  # both or battery_only
MERGE_LMFP_INTO_LFP = True

# If the same HS code appears in adjacent transitions, use its raw bilateral
# records once. "downstream" assigns them to the latest transition shown.
SHARED_HS_TRADE_OWNER = "downstream"

# Optional chemistry-specific factors for the shared cathode/battery trade.
# If empty, POST_TRADE_HS factors are retained.
CHEMISTRY_CONVERSION_FACTORS = {
    # "LFP": 0.20,
    # "LMFP": 0.20,
    # "NMC": 0.40,
    # "NCA": 0.40,
}

# True uses production quantities exactly as before. False uses production
# workbooks only for positive-production country lists and cathode chemistry
# shares; all production node sizes are then inferred from converted trade and
# cross-stage material balance.
USE_PRODUCTION_DATA = True

# Enter HS codes as strings so leading zeroes are never lost. An empty mapping
# means that this post-trade step has no participating trade data; balance
# calculation will still continue with imports and exports set to zero.
# The 1.0 values below are runnable examples only, not recommended coefficients.
# With the default six-stage chain the transition keys are:
# 1 mining->processing, 2 processing->refining, 3 refining->pcam,
# 4 pcam->cathode, 5 cathode->battery. Keys shift automatically when stages
# are merged/hidden. Repeating an HS code uses its records only at the owner
# selected by SHARED_HS_TRADE_OWNER.

# Li-full
POST_TRADE_HS = {
    "post_trade_1": {
        "253090": 0.03,
    },
    "post_trade_2": {},
    "post_trade_3": {
        "282520": 0.165,
        "283691": 0.188,
    },
}

POST_TRADE_PRODUCTS = {
    "post_trade_3": {
        "282520": "Lithium Hydroxide",
        "283691": "Lithium Carbonate",
    },
}

# Co-full
# POST_TRADE_HS = {
#     "post_trade_1": {
#         "260500": 0.15,
#     },
#     "post_trade_2": {
#         "282200": 0.329,
#         "810520": 0.6,
#         "810530": 0.6,
#     },
#     "post_trade_3": {
#         "283329": 0.03,
#     },
# }

# Co-intermediate
# POST_TRADE_HS = {
#     "post_trade_1": {
#         "260400": 0.015,
#     },
#     "post_trade_2": {
#         "282200": 0.329,
#         "810520": 0.6,
#         "810530": 0.6,
#         "283329": 0.03,
#     },
# }

# Ni-full
# POST_TRADE_HS = {
#     "post_trade_1": {
#         "260400": 0.015,
#     },
#     "post_trade_2": {
#         "750110": 0.75,
#         "750120": 0.55,
#         "750300": 0.5,
#         "750400": 0.995,
#     },
#     "post_trade_3": {
#         "283324": 0.223,
#     },
# }

# Ni-intermediate
# POST_TRADE_HS = {
#     "post_trade_1": {
#         "260400": 0.015,
#     },
#     "post_trade_2": {
#         "750110": 0.75,
#         "750120": 0.55,
#         "750300": 0.5,
#         "750400": 0.995,
#         "283324": 0.223,
#     },
# }

# Map each production stage to one of the named workbooks below. Only stages in
# the active route are required. Missing workbooks or metal/stage sheets raise
# an error; the program never falls back to another source silently.
PRODUCTION_SOURCE_BY_STAGE = {
    "mining": "scinsight",       # may also use usgs, ma_2026, or benchmark
    "processing": "scinsight",
    "refining": "scinsight",
    "pro_ref": "scinsight",      # used when processing/refining are merged
    "pcam": "scinsight",
    "cathode": "scinsight",
    "battery": "scinsight",
}

# Backward-compatible fallback for older config files that do not define
# PRODUCTION_SOURCE_BY_STAGE.
PRODUCTION_SOURCE = "scinsight"
PRODUCTION_ROOTS = {
    "usgs": DATA_ROOT / "production" / "USGS_production_data.xlsx",
    "scinsight": DATA_ROOT / "production" / "scinsight_production_data.xlsx",
    "ma_2026": DATA_ROOT / "production" / "ma_2026_production_data.xlsx",
    "benchmark": DATA_ROOT / "production" / "benchmark_production_data.xlsx",
}

# These sources contain only status=all. They always use that status even when
# PRODUCTION_SHEETS below requests operating/probable statuses for other stages.
PRODUCTION_ALL_STATUS_SOURCES = {"usgs", "ma_2026"}

# "all" sums every available status in SCInsight/Benchmark. Otherwise list the
# statuses to sum, for example ["operating", "highly probable"]. USGS/MA remain
# fixed at status=all.
PRODUCTION_SHEETS = "all"
TRADE_ROOT = DATA_ROOT
REFERENCE_FILE = DATA_ROOT / "reference" / "ListOfreference.xlsx"

# Each run creates a new timestamped folder here. Every output filename contains
# metal, year, canonical route, and the active stage/source selection.
OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"

# These values mirror the web viewer's static-image defaults and layout choices.
REFERENCE_QUANTITY = 10000
THEME = "light"
SORT_MODE = "size"  # size or continent
IMAGE_WIDTH = 2200
IMAGE_SCALE = 1.0

# Font size for node/country labels, stage titles (Mining, Processing, etc.),
# post-trade titles, and the reference-quantity label in PNG and HTML outputs.
LABEL_FONT_SIZE = 20
