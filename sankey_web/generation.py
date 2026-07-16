from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import settings
from .inventory import session_storage_key, source_paths, validate_session_id


def _load_core() -> tuple[Any, Any]:
    core_root = settings.MANUAL_CORE_ROOT.resolve()
    if not core_root.exists():
        raise FileNotFoundError(f"Manual Sankey core does not exist: {core_root}")
    core_text = str(core_root)
    if core_text not in sys.path:
        sys.path.insert(0, core_text)
    return importlib.import_module("pipeline"), importlib.import_module("routes")


def active_route(payload: dict[str, Any]) -> dict[str, Any]:
    _, routes = _load_core()
    route = routes.route_from_options(
        bool(payload.get("mergeProcessingRefining", False)),
        bool(payload.get("showPcam", True)),
        bool(payload.get("showBattery", True)),
    )
    return {
        "key": route.key,
        "stages": [{"key": stage.key, "label": stage.label} for stage in route.production_stages],
        "transitions": [
            {
                "key": transition.key,
                "label": transition.label,
                "source": transition.source_stage,
                "target": transition.target_stage,
            }
            for transition in route.transitions
        ],
    }


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{name} must be at least {minimum}.")
    return result


def _trade_configuration(payload: dict[str, Any], route: dict[str, Any]) -> tuple[dict, dict]:
    rows = payload.get("tradeRows") or []
    expected = {transition["key"] for transition in route["transitions"]}
    hs: dict[str, dict[str, float]] = {key: {} for key in expected}
    products: dict[str, dict[str, str]] = {}
    for row in rows:
        transition = str(row.get("transition") or "").strip()
        code = str(row.get("hsCode") or "").strip()
        if not code:
            continue
        if transition not in expected:
            raise ValueError(f"Trade row uses inactive transition: {transition}")
        if not code.isdigit():
            raise ValueError(f"HS code must contain digits only: {code!r}")
        factor = _number(row.get("factor"), f"Conversion factor for HS {code}", minimum=0.0)
        hs[transition][code] = factor
        product = str(row.get("product") or "").strip()
        if product:
            products.setdefault(transition, {})[code] = product
    return hs, products


def _config_module(payload: dict[str, Any], session_id: str, output_root: Path) -> SimpleNamespace:
    route = active_route(payload)
    roots = source_paths(session_id)
    source_by_stage = {
        str(stage): str(source).strip().lower()
        for stage, source in dict(payload.get("productionSources") or {}).items()
    }
    for stage in route["stages"]:
        stage_key = stage["key"]
        source_key = source_by_stage.get(stage_key, "")
        if not source_key:
            raise ValueError(f"Choose a production source for {stage['label']}.")
        if source_key not in roots:
            raise ValueError(f"Unknown production source for {stage['label']}: {source_key}")
        if roots[source_key] is None:
            raise ValueError(f"Upload {settings.SOURCE_DEFINITIONS[source_key]['label']} before using it.")

    trade_hs, trade_products = _trade_configuration(payload, route)
    statuses = payload.get("productionStatuses", "all")
    if isinstance(statuses, list):
        statuses = [str(status).strip() for status in statuses if str(status).strip()]
        if not statuses:
            statuses = "all"
    chemistry_factors = {
        str(key).strip().upper(): _number(value, f"Chemistry factor {key}", minimum=0.0)
        for key, value in dict(payload.get("chemistryFactors") or {}).items()
        if str(value).strip() != ""
    }
    existing_roots = {key: path for key, path in roots.items() if path is not None}
    first_source = next(iter(source_by_stage.values()))
    stage_aliases = {
        "mining": "m",
        "processing": "p",
        "refining": "r",
        "pro_ref": "i",
        "pcam": "pc",
        "cathode": "c",
        "battery": "b",
    }
    source_aliases = {"usgs": "usgs", "ma_2026": "ma", "scinsight": "sci", "benchmark": "bm"}
    source_tag = "-".join(
        f"{stage_aliases[stage['key']]}_{source_aliases[source_by_stage[stage['key']]]}"
        for stage in route["stages"]
    )
    route_tag = "merged" if bool(payload.get("mergeProcessingRefining", False)) else "full"
    if not bool(payload.get("showPcam", True)):
        route_tag += "-no_pc"
    if not bool(payload.get("showBattery", True)):
        route_tag += "-no_b"
    output_basename = f"{str(payload.get('metal') or 'Ni')}_{int(payload.get('year') or 2024)}_{route_tag}_{source_tag}"
    return SimpleNamespace(
        METAL=str(payload.get("metal") or "Ni"),
        YEAR=int(payload.get("year") or 2024),
        ROUTE="full",
        MERGE_PROCESSING_REFINING=bool(payload.get("mergeProcessingRefining", False)),
        SHOW_PCAM=bool(payload.get("showPcam", True)),
        SHOW_BATTERY=bool(payload.get("showBattery", True)),
        NODE_VIEW=str(payload.get("nodeView") or "country"),
        COUNTRY_LABEL_MODE=str(payload.get("countryLabelMode") or "full"),
        FLOW_TRANSPARENCY_THRESHOLD=_number(
            payload.get("flowTransparencyThreshold", 0),
            "Flow transparency threshold",
            minimum=0.0,
        ),
        NODE_TRANSPARENCY_THRESHOLD=_number(
            payload.get("nodeTransparencyThreshold", 0),
            "Node transparency threshold",
            minimum=0.0,
        ),
        PRESERVE_COUNTRY_IDS=[int(value) for value in payload.get("preservedCountryIds", [])],
        CHEMISTRY_STAGE_SCOPE=str(payload.get("chemistryStageScope") or "both"),
        MERGE_LMFP_INTO_LFP=bool(payload.get("mergeLmfpIntoLfp", True)),
        SHARED_HS_TRADE_OWNER=str(payload.get("sharedHsTradeOwner") or "downstream"),
        CHEMISTRY_CONVERSION_FACTORS=chemistry_factors,
        USE_PRODUCTION_DATA=bool(payload.get("useProductionData", True)),
        POST_TRADE_HS=trade_hs,
        POST_TRADE_PRODUCTS=trade_products,
        PRODUCTION_SOURCE_BY_STAGE=source_by_stage,
        PRODUCTION_SOURCE=first_source,
        PRODUCTION_ROOTS=existing_roots,
        PRODUCTION_ALL_STATUS_SOURCES=set(settings.ALL_STATUS_SOURCE_KEYS),
        PRODUCTION_SHEETS=statuses,
        TRADE_ROOT=settings.TRADE_ROOT,
        REFERENCE_FILE=settings.REFERENCE_FILE,
        OUTPUT_ROOT=output_root,
        REFERENCE_QUANTITY=_number(payload.get("referenceQuantity", 10000), "Reference quantity", minimum=1.0),
        THEME="light",
        SORT_MODE=str(payload.get("sortMode") or "size"),
        IMAGE_WIDTH=int(_number(payload.get("imageWidth", 2200), "Image width", minimum=600)),
        IMAGE_SCALE=_number(payload.get("imageScale", 1.0), "Image scale", minimum=0.1),
        LABEL_FONT_SIZE=int(_number(payload.get("labelFontSize", 16), "Label font size", minimum=8)),
        OUTPUT_BASENAME=output_basename,
    )


def generate(payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    session_id = validate_session_id(session_id)
    pipeline, _ = _load_core()
    output_root = settings.ARTIFACT_ROOT / session_storage_key(session_id)
    output_root.mkdir(parents=True, exist_ok=True)
    module = _config_module(payload, session_id, output_root)
    configured = pipeline.settings_from_module(module)
    outputs = pipeline.run_pipeline(configured)
    manifest = json.loads(Path(outputs["manifest"]).read_text(encoding="utf-8"))
    return {"outputs": outputs, "manifest": manifest, "route": active_route(payload)}
