from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("SANKEY_DATA_ROOT", str(PROJECT_ROOT / "data")))
MANUAL_CORE_ROOT = Path(
    os.environ.get(
        "MANUAL_SANKEY_CORE_ROOT",
        str(PROJECT_ROOT / "sankey_core"),
    )
)
TRADE_ROOT = Path(os.environ.get("SANKEY_TRADE_ROOT", str(DATA_ROOT)))
REFERENCE_FILE = Path(
    os.environ.get(
        "SANKEY_REFERENCE_FILE",
        str(DATA_ROOT / "reference" / "ListOfreference.xlsx"),
    )
)

SOURCE_DEFINITIONS = {
    "usgs": {
        "label": "USGS",
        "path": DATA_ROOT / "production" / "USGS_production_data.xlsx",
        "uploadRequired": False,
        "allStatusOnly": True,
        "description": "Public mining production series",
    },
    "ma_2026": {
        "label": "Ma et al., 2026",
        "path": DATA_ROOT / "production" / "ma_2026_production_data.xlsx",
        "uploadRequired": False,
        "allStatusOnly": True,
        "description": "Public historical production estimates from Ma et al. (2026)",
    },
    "scinsight": {
        "label": "SCInsight",
        "path": None,
        "uploadRequired": True,
        "allStatusOnly": False,
        "description": "Upload for this browser tab",
    },
    "benchmark": {
        "label": "Benchmark",
        "path": None,
        "uploadRequired": True,
        "allStatusOnly": False,
        "description": "Upload for this browser tab",
    },
}

UPLOAD_SOURCE_KEYS = frozenset({"scinsight", "benchmark"})
ALL_STATUS_SOURCE_KEYS = frozenset({"usgs", "ma_2026"})
RUNTIME_ROOT = PROJECT_ROOT / ".runtime"
UPLOAD_ROOT = RUNTIME_ROOT / "uploads"
ARTIFACT_ROOT = RUNTIME_ROOT / "artifacts"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SUPPORTED_METALS = ("Li", "Co", "Ni", "Mn")
STAGE_ORDER = ("mining", "processing", "refining", "pro_ref", "pcam", "cathode", "battery")
