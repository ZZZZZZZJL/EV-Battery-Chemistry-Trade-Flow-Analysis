from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd

from flow_builder import build_flow_graph
from loaders import load_production, load_reference, load_trade_records, normalize_metal
from models import Settings
from renderer import make_figure
from routes import display_stages, route_for, route_from_options


CATHODE_VIEW_ALIASES = {
    "country": "country",
    "chemistry": "chemistry_only",
    "chemistry_only": "chemistry_only",
    "country_chemistry": "country_chemistry",
    "country_and_chemistry": "country_chemistry",
    "each_country_chemistry": "country_chemistry",
}

CONVERSION_COLUMNS = [
    "metal",
    "year",
    "route",
    "transition",
    "transition_label",
    "trade_data_direction",
    "hs_code",
    "target_product",
    "chemistry_factor_basis",
    "chemistry_factor_detail",
    "importer_id",
    "importer_name",
    "exporter_id",
    "exporter_name",
    "classification",
    "raw_quantity_tonnes",
    "manual_conversion_factor",
    "configured_conversion_factor",
    "converted_quantity_before_scaling",
    "available_source_production",
    "exporter_total_before_scaling",
    "production_scaling_multiplier",
    "effective_conversion_factor",
    "final_trade_quantity_tonnes",
    "included_in_sankey",
    "adjustment_reason",
    "source_files",
]

BALANCE_COLUMNS = [
    "metal",
    "year",
    "route",
    "node_basis_mode",
    "transition",
    "transition_label",
    "country_id",
    "country_name",
    "source_stage",
    "target_stage",
    "source_production",
    "target_production",
    "trade_exports",
    "trade_imports",
    "producer_to_producer_imports",
    "from_non_source_imports",
    "trade_exports_to_non_target",
    "domestic_flow",
    "untraded_production_to_non_target",
    "unknown_source",
    "excess_to_unknown_destination",
    "source_balance_residual",
    "post_trade_balance_residual",
]

STAGE_COLUMNS = [
    "metal",
    "year",
    "route",
    "node_basis_mode",
    "country_id",
    "country_name",
    "production_stage",
    "is_in_stage_list",
    "trade_import",
    "trade_export",
    "domestic_from_upstream",
    "domestic_to_downstream",
    "unknown_source",
    "unknown_destination",
    "intrinsic_chain_source",
    "terminal_chain_absorption",
    "node_size",
    "material_balance_residual",
]

PRODUCTION_SHEET_COLUMNS = [
    "production_source",
    "metal",
    "year",
    "route",
    "stage",
    "workbook",
    "stage_sheet",
    "sheet",
    "row_count",
    "selected_year_total",
]


def _setting(module: ModuleType, name: str) -> Any:
    if not hasattr(module, name):
        raise ValueError(f"Configuration is missing required setting {name}.")
    return getattr(module, name)


def _as_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be True or False.")


def _production_sheets(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        text = value.strip()
        if text.lower() == "all":
            return None
        values = [text]
    else:
        try:
            values = [str(item).strip() for item in value]
        except TypeError as exc:
            raise ValueError("PRODUCTION_SHEETS must be 'all' or a non-empty list of sheet names.") from exc
    if not values or any(not item for item in values):
        raise ValueError("PRODUCTION_SHEETS must be 'all' or a non-empty list of sheet names.")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        key = item.casefold()
        if key not in seen:
            normalized.append(item)
            seen.add(key)
    return tuple(normalized)


def _production_source_tag(settings: Settings, route: Any) -> str:
    by_stage = settings.production_sources_by_stage or {
        stage.key: settings.production_source for stage in route.production_stages
    }
    ordered = [(stage.key, by_stage[stage.key]) for stage in route.production_stages]
    unique_sources = {source for _, source in ordered}
    if len(unique_sources) == 1:
        return re.sub(r"[^a-z0-9]+", "_", ordered[0][1].casefold()).strip("_")
    return "_".join(
        f"{re.sub(r'[^a-z0-9]+', '_', stage.casefold()).strip('_')}-"
        f"{re.sub(r'[^a-z0-9]+', '_', source.casefold()).strip('_')}"
        for stage, source in ordered
    )


def settings_from_module(module: ModuleType) -> Settings:
    metal = normalize_metal(_setting(module, "METAL"))
    has_dynamic_route = all(
        hasattr(module, name)
        for name in ("MERGE_PROCESSING_REFINING", "SHOW_PCAM", "SHOW_BATTERY")
    )
    merge_processing_refining = _as_bool(
        getattr(module, "MERGE_PROCESSING_REFINING", False), "MERGE_PROCESSING_REFINING"
    )
    show_pcam = _as_bool(getattr(module, "SHOW_PCAM", False), "SHOW_PCAM")
    show_battery = _as_bool(getattr(module, "SHOW_BATTERY", False), "SHOW_BATTERY")
    if has_dynamic_route:
        route_spec = route_from_options(merge_processing_refining, show_pcam, show_battery)
    else:
        requested_route = str(_setting(module, "ROUTE")).strip().lower()
        route_spec = route_for(requested_route)
    route = route_spec.key
    raw_view = str(getattr(module, "NODE_VIEW", getattr(module, "CATHODE_VIEW", "country"))).strip().lower()
    try:
        cathode_view = CATHODE_VIEW_ALIASES[raw_view]
    except KeyError as exc:
        raise ValueError(
            "NODE_VIEW must be country, chemistry/chemistry_only, or country_chemistry."
        ) from exc
    country_label_mode = str(getattr(module, "COUNTRY_LABEL_MODE", "full")).strip().lower()
    if country_label_mode not in {"full", "iso3"}:
        raise ValueError("COUNTRY_LABEL_MODE must be 'full' or 'iso3'.")
    raw_preserved_country_ids = getattr(module, "PRESERVE_COUNTRY_IDS", ())
    try:
        preserved_country_ids = frozenset(int(value) for value in raw_preserved_country_ids)
    except (TypeError, ValueError) as exc:
        raise ValueError("PRESERVE_COUNTRY_IDS must contain numeric country ids.") from exc
    post_trade_hs = {
        str(key): {str(hs): float(factor) for hs, factor in dict(value).items()}
        for key, value in dict(_setting(module, "POST_TRADE_HS")).items()
    }
    expected = {transition.key for transition in route_spec.transitions}
    unknown = sorted(set(post_trade_hs) - expected)
    if unknown:
        raise ValueError(
            f"POST_TRADE_HS contains steps that are not part of route={route}: {unknown}. "
            f"Expected only: {sorted(expected)}"
        )
    for transition_key in expected:
        post_trade_hs.setdefault(transition_key, {})
    raw_products = getattr(module, "POST_TRADE_PRODUCTS", {})
    post_trade_products = {
        str(step): {str(hs).strip(): str(product).strip() for hs, product in dict(mapping).items()}
        for step, mapping in dict(raw_products).items()
    }
    unknown_product_steps = sorted(set(post_trade_products) - expected)
    if unknown_product_steps:
        raise ValueError(
            f"POST_TRADE_PRODUCTS contains steps outside route={route}: {unknown_product_steps}"
        )
    for step, mapping in post_trade_products.items():
        unknown_codes = sorted(set(mapping) - set(post_trade_hs.get(step, {})))
        if unknown_codes:
            raise ValueError(
                f"POST_TRADE_PRODUCTS[{step!r}] contains HS codes absent from POST_TRADE_HS: {unknown_codes}"
            )
        blank_products = sorted(hs for hs, product in mapping.items() if not product)
        if blank_products:
            raise ValueError(f"Blank target product for HS codes: {blank_products}")
    raw_production_roots = dict(_setting(module, "PRODUCTION_ROOTS"))
    production_roots = {
        str(source).strip().lower(): Path(path).expanduser().resolve()
        for source, path in raw_production_roots.items()
    }
    if not production_roots or any(not source for source in production_roots):
        raise ValueError("PRODUCTION_ROOTS must contain at least one named production source.")

    raw_source_by_stage = getattr(module, "PRODUCTION_SOURCE_BY_STAGE", None)
    if raw_source_by_stage is None:
        legacy_source = str(_setting(module, "PRODUCTION_SOURCE")).strip().lower()
        production_sources_by_stage = {
            stage.key: legacy_source for stage in route_spec.production_stages
        }
    else:
        production_sources_by_stage = {
            str(stage).strip().lower(): str(source).strip().lower()
            for stage, source in dict(raw_source_by_stage).items()
        }
        known_stages = {"mining", "processing", "refining", "pro_ref", "pcam", "cathode", "battery"}
        unknown_stages = sorted(set(production_sources_by_stage) - known_stages)
        if unknown_stages:
            raise ValueError(
                "PRODUCTION_SOURCE_BY_STAGE contains unsupported stage name(s): "
                f"{unknown_stages}. Choose from: {sorted(known_stages)}"
            )
        missing_stages = [
            stage.key for stage in route_spec.production_stages
            if stage.key not in production_sources_by_stage
        ]
        if missing_stages:
            raise ValueError(
                f"PRODUCTION_SOURCE_BY_STAGE is missing active route stage(s): {missing_stages}"
            )

    active_sources = {
        stage.key: production_sources_by_stage[stage.key]
        for stage in route_spec.production_stages
    }
    unknown_sources = sorted(set(active_sources.values()) - set(production_roots))
    if unknown_sources:
        raise ValueError(
            f"Unknown production source(s) in PRODUCTION_SOURCE_BY_STAGE: {unknown_sources}. "
            f"Choose from: {', '.join(sorted(production_roots))}"
        )
    blank_source_stages = sorted(stage for stage, source in active_sources.items() if not source)
    if blank_source_stages:
        raise ValueError(
            f"PRODUCTION_SOURCE_BY_STAGE has blank source(s) for stage(s): {blank_source_stages}"
        )
    unique_active_sources = sorted(set(active_sources.values()))
    production_source = unique_active_sources[0] if len(unique_active_sources) == 1 else "mixed"
    legacy_root = production_roots[unique_active_sources[0]]
    raw_all_status_sources = getattr(module, "PRODUCTION_ALL_STATUS_SOURCES", None)
    if raw_all_status_sources is None:
        all_status_sources = frozenset({"usgs", "ma_2026"} & set(production_roots))
    else:
        all_status_sources = frozenset(
            str(source).strip().lower() for source in raw_all_status_sources
        )
    unknown_all_status_sources = sorted(all_status_sources - set(production_roots))
    if unknown_all_status_sources:
        raise ValueError(
            "PRODUCTION_ALL_STATUS_SOURCES contains unknown source(s): "
            f"{unknown_all_status_sources}"
        )
    settings = Settings(
        metal=metal,
        year=int(_setting(module, "YEAR")),
        route=route,
        merge_processing_refining=merge_processing_refining,
        show_pcam=show_pcam,
        show_battery=show_battery,
        cathode_view=cathode_view,
        chemistry_stage_scope=str(getattr(module, "CHEMISTRY_STAGE_SCOPE", "both")).strip().lower(),
        merge_lmfp_into_lfp=_as_bool(getattr(module, "MERGE_LMFP_INTO_LFP", True), "MERGE_LMFP_INTO_LFP"),
        shared_hs_trade_owner=str(getattr(module, "SHARED_HS_TRADE_OWNER", "downstream")).strip().lower(),
        chemistry_conversion_factors={
            str(key).strip().upper(): float(value)
            for key, value in dict(getattr(module, "CHEMISTRY_CONVERSION_FACTORS", {})).items()
        },
        use_production_data=_as_bool(_setting(module, "USE_PRODUCTION_DATA"), "USE_PRODUCTION_DATA"),
        production_source=production_source,
        production_sheets=_production_sheets(_setting(module, "PRODUCTION_SHEETS")),
        production_root=legacy_root,
        trade_root=Path(_setting(module, "TRADE_ROOT")).expanduser().resolve(),
        reference_file=Path(_setting(module, "REFERENCE_FILE")).expanduser().resolve(),
        post_trade_hs=post_trade_hs,
        post_trade_products=post_trade_products,
        output_root=Path(_setting(module, "OUTPUT_ROOT")).expanduser().resolve(),
        reference_quantity=float(_setting(module, "REFERENCE_QUANTITY")),
        theme=str(_setting(module, "THEME")).strip().lower(),
        sort_mode=str(_setting(module, "SORT_MODE")).strip().lower(),
        image_width=int(_setting(module, "IMAGE_WIDTH")),
        image_scale=float(_setting(module, "IMAGE_SCALE")),
        label_font_size=int(_setting(module, "LABEL_FONT_SIZE")),
        production_sources_by_stage=active_sources,
        production_roots=production_roots,
        production_all_status_sources=all_status_sources,
        output_basename=(
            re.sub(r"[^A-Za-z0-9_.-]+", "_", str(getattr(module, "OUTPUT_BASENAME", "")).strip()).strip("_.-")
            or None
        ),
        country_label_mode=country_label_mode,
        flow_transparency_threshold=float(getattr(module, "FLOW_TRANSPARENCY_THRESHOLD", 0.0)),
        node_transparency_threshold=float(getattr(module, "NODE_TRANSPARENCY_THRESHOLD", 0.0)),
        preserved_country_ids=preserved_country_ids,
    )
    if settings.year < 1900 or settings.year > 2200:
        raise ValueError(f"YEAR is outside the supported range: {settings.year}")
    if not math.isfinite(settings.reference_quantity) or settings.reference_quantity <= 0:
        raise ValueError("REFERENCE_QUANTITY must be finite and greater than zero.")
    if settings.image_width <= 0 or settings.image_scale <= 0:
        raise ValueError("IMAGE_WIDTH and IMAGE_SCALE must be greater than zero.")
    if settings.label_font_size <= 0:
        raise ValueError("LABEL_FONT_SIZE must be greater than zero.")
    if (
        not math.isfinite(settings.flow_transparency_threshold)
        or not math.isfinite(settings.node_transparency_threshold)
        or settings.flow_transparency_threshold < 0
        or settings.node_transparency_threshold < 0
    ):
        raise ValueError("Transparency thresholds must be finite and non-negative.")
    if settings.chemistry_stage_scope not in {"both", "battery_only"}:
        raise ValueError("CHEMISTRY_STAGE_SCOPE must be 'both' or 'battery_only'.")
    if settings.shared_hs_trade_owner not in {"downstream", "upstream"}:
        raise ValueError("SHARED_HS_TRADE_OWNER must be 'downstream' or 'upstream'.")
    return settings


def _output_paths(output_image: Path) -> dict[str, Path]:
    stem = output_image.with_suffix("")
    return {
        "html": stem.parent / f"{stem.name}.html",
        "conversion": stem.parent / f"{stem.name}_conversion_factors.csv",
        "balance": stem.parent / f"{stem.name}_balance_audit.csv",
        "ignored": stem.parent / f"{stem.name}_ignored_production_rows.csv",
        "stage": stem.parent / f"{stem.name}_stage_material_flow.csv",
        "production_sheets": stem.parent / f"{stem.name}_production_sheet_summary.csv",
        "manifest": stem.parent / f"{stem.name}_manifest.json",
    }


def _write_csv(rows: tuple[dict[str, Any], ...], columns: list[str], path: Path) -> None:
    frame = pd.DataFrame(list(rows), columns=columns)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _verify_balance(
    rows: tuple[dict[str, Any], ...],
    stage_rows: tuple[dict[str, Any], ...],
) -> dict[str, float]:
    max_source = max((abs(float(row["source_balance_residual"])) for row in rows), default=0.0)
    max_post = max((abs(float(row["post_trade_balance_residual"])) for row in rows), default=0.0)
    max_stage = max(
        (abs(float(row["material_balance_residual"])) for row in stage_rows),
        default=0.0,
    )
    tolerance = 1e-6
    if max_source > tolerance or max_post > tolerance or max_stage > tolerance:
        raise ValueError(
            f"Balance verification failed: max_source_residual={max_source}, "
            f"max_post_trade_residual={max_post}, max_stage_residual={max_stage}"
        )
    return {
        "max_source_balance_residual": max_source,
        "max_post_trade_balance_residual": max_post,
        "max_stage_material_balance_residual": max_stage,
    }


def run_pipeline(settings: Settings) -> dict[str, str]:
    route = route_from_options(
        settings.merge_processing_refining, settings.show_pcam, settings.show_battery
    ) if settings.route.startswith(("full", "merged")) else route_for(settings.route)
    stages = display_stages(route)
    production = load_production(settings, route)
    trade_by_transition = {
        transition.key: load_trade_records(settings, transition.key)
        for transition in route.transitions
    }
    ordered = list(route.transitions)
    claimed: set[str] = set()
    ownership_order = reversed(ordered) if settings.shared_hs_trade_owner == "downstream" else ordered
    for transition in ownership_order:
        kept = []
        for record in trade_by_transition[transition.key]:
            if record.hs_code in claimed:
                continue
            kept.append(record)
        claimed.update(record.hs_code for record in kept)
        trade_by_transition[transition.key] = kept
    required_ids = {
        country_id
        for mapping in production.totals.values()
        for country_id in mapping
    }
    for records in trade_by_transition.values():
        for record in records:
            required_ids.add(record.importer_id)
            required_ids.add(record.exporter_id)
    reference = load_reference(settings.reference_file, required_ids)
    result = build_flow_graph(settings, route, production, reference, trade_by_transition)
    balance_check = _verify_balance(result.balance_rows, result.stage_rows)
    figure = make_figure(
        nodes=result.nodes,
        links=result.links,
        stages=stages,
        metal=settings.metal,
        route=route.key,
        reference_quantity=settings.reference_quantity,
        theme=settings.theme,
        sort_mode=settings.sort_mode,
        label_font_size=settings.label_font_size,
        flow_transparency_threshold=settings.flow_transparency_threshold,
        node_transparency_threshold=settings.node_transparency_threshold,
        preserved_country_ids=settings.preserved_country_ids,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    source_tag = _production_source_tag(settings, route)
    basename = settings.output_basename or f"{settings.metal}_{settings.year}_{route.key}_{source_tag}"
    if settings.output_basename is None and settings.production_sheets is not None:
        sheet_tag = "-".join(
            re.sub(r"[^a-z0-9]+", "_", sheet.casefold()).strip("_")
            for sheet in settings.production_sheets
        )
        basename = f"{basename}_{sheet_tag}"
    run_directory = settings.output_root / f"{basename}_{timestamp}"
    run_directory.mkdir(parents=True, exist_ok=False)
    output_image = run_directory / f"{basename}.png"
    paths = _output_paths(output_image)
    try:
        figure.write_image(
            str(output_image),
            format="png",
            width=settings.image_width,
            scale=settings.image_scale,
        )
    except Exception as exc:
        message = str(exc)
        if "kaleido" in message.lower() or "chrome" in message.lower():
            raise RuntimeError(
                "PNG export requires Kaleido and a Chrome-compatible browser. "
                "Install this folder's requirements in the selected VS Code/PyCharm interpreter."
            ) from exc
        raise

    figure.write_html(
        str(paths["html"]),
        include_plotlyjs=True,
        full_html=True,
        config={"responsive": True, "displaylogo": False},
    )

    _write_csv(result.conversion_rows, CONVERSION_COLUMNS, paths["conversion"])
    _write_csv(result.balance_rows, BALANCE_COLUMNS, paths["balance"])
    _write_csv(result.stage_rows, STAGE_COLUMNS, paths["stage"])
    _write_csv(production.sheet_summary_rows, PRODUCTION_SHEET_COLUMNS, paths["production_sheets"])
    ignored_frame = pd.DataFrame(
        list(production.ignored_rows),
        columns=["stage", "file", "sheet", "description", "reason"],
    )
    ignored_frame.to_csv(paths["ignored"], index=False, encoding="utf-8-sig")
    manifest = {
        "metal": settings.metal,
        "year": settings.year,
        "route": route.key,
        "merge_processing_refining": settings.merge_processing_refining,
        "show_pcam": settings.show_pcam,
        "show_battery": settings.show_battery,
        "cathode_view": settings.cathode_view,
        "country_label_mode": settings.country_label_mode,
        "flow_transparency_threshold": settings.flow_transparency_threshold,
        "node_transparency_threshold": settings.node_transparency_threshold,
        "preserved_country_ids": sorted(settings.preserved_country_ids),
        "chemistry_stage_scope": settings.chemistry_stage_scope,
        "merge_lmfp_into_lfp": settings.merge_lmfp_into_lfp,
        "shared_hs_trade_owner": settings.shared_hs_trade_owner,
        "chemistry_conversion_factors": settings.chemistry_conversion_factors,
        "use_production_data": settings.use_production_data,
        "production_source": settings.production_source,
        "production_source_by_stage": settings.production_sources_by_stage or {
            stage.key: settings.production_source for stage in route.production_stages
        },
        "production_path_by_stage": {
            stage.key: str(
                (settings.production_roots or {settings.production_source: settings.production_root})[
                    (settings.production_sources_by_stage or {
                        item.key: settings.production_source for item in route.production_stages
                    })[stage.key]
                ]
            )
            for stage in route.production_stages
        },
        "production_all_status_sources": sorted(settings.production_all_status_sources),
        "production_sheets_requested": "all" if settings.production_sheets is None else list(settings.production_sheets),
        "production_sheets_by_stage": {
            stage.key: list(dict.fromkeys(
                row["sheet"] for row in production.sheet_summary_rows if row["stage"] == stage.key
            ))
            for stage in route.production_stages
        },
        "production_values_used_for_node_size": settings.use_production_data,
        "production_membership_basis": "selected-year positive production",
        "chemistry_share_source": "selected-year production workbook",
        "production_root": str(settings.production_root) if settings.production_source != "mixed" else None,
        "trade_root": str(settings.trade_root),
        "reference_file": str(settings.reference_file),
        "post_trade_hs": settings.post_trade_hs,
        "post_trade_products": settings.post_trade_products,
        "display_stages": [{"key": stage.key, "label": stage.label} for stage in stages],
        "trade_record_counts": {
            transition: len(records) for transition, records in trade_by_transition.items()
        },
        "ignored_production_rows": len(production.ignored_rows),
        "nodes": len(result.nodes),
        "links_before_render_aggregation": len(result.links),
        "conversion_rows": len(result.conversion_rows),
        "balance_rows": len(result.balance_rows),
        "stage_material_flow_rows": len(result.stage_rows),
        "label_font_size": settings.label_font_size,
        "image_background": "#FFFFFF",
        "balance_verification": balance_check,
        "outputs": {
            "run_directory": str(run_directory),
            "image": str(output_image),
            **{key: str(path) for key, path in paths.items()},
        },
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "run_directory": str(run_directory),
        "image": str(output_image),
        **{key: str(path) for key, path in paths.items()},
    }
