from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import re
from typing import Any

import plotly.graph_objects as go

from trade_flow.baseline import pipeline_v1
from trade_flow.legacy_site.services import cobalt_sankey, lithium_sankey, nickel_sankey
from trade_flow.legacy_site.services.cobalt_data import CobaltYearInputs, TradeFlow as CobaltTradeFlow
from trade_flow.legacy_site.services.lithium_data import LithiumYearInputs, TradeFlow as LithiumTradeFlow
from trade_flow.legacy_site.services.nickel_data import NickelYearInputs, TradeFlow as NickelTradeFlow
from trade_flow.legacy_site.services.precomputed_repository import (
    OutputRepository,
    SCENARIO_LABELS,
    TABLE_VIEW_LABELS,
    get_repository,
)
from trade_flow.legacy_site.services.shared_sankey import (
    BODY_TEXT_BY_THEME,
    BOTTOM_BAND_PX,
    DEFAULT_REFERENCE_QTY as SANKEY_DEFAULT_REFERENCE_QTY,
    DEFAULT_THEME as SANKEY_DEFAULT_THEME,
    GAP_PX,
    MIN_STAGE_HEIGHT_PX,
    PLOTLY_NODE_PAD_PX,
    REFERENCE_LABEL_GAP_PAPER,
    REFERENCE_NODE_CENTER_X,
    REFERENCE_NODE_HALF_WIDTH_PAPER,
    REFERENCE_NODE_HEIGHT_PX,
    REFERENCE_TEXT_BY_THEME,
    REGION_COLORS,
    REGION_ORDER,
    LinkSpec,
    NodeSpec,
    SPECIAL_COLORS,
    STAGE_NAMES,
    STAGE_LABELS,
    STAGE_ORDER,
    STAGE_TITLE_Y_RATIO,
    THEME_MODES,
    TOP_BAND_PX,
    TITLE_TEXT_BY_THEME,
    X_MAP,
    _apply_stage_aggregation as _shared_apply_stage_aggregation,
    _build_figure as _shared_build_figure,
    _validate_aggregate_counts as _shared_validate_aggregate_counts,
)


DEFAULT_METAL = "Ni"
RESULT_MODES = ("baseline", "first_optimization")
SORT_MODES = ("size", "manual", "continent")
SPECIAL_NODE_POSITIONS = ("first", "last")
DEFAULT_SPECIAL_POSITION = "first"
DEFAULT_THEME = "light"
DEFAULT_REFERENCE_QTY_BY_METAL = {
    "Ni": 1_000_000.0,
    "Li": 50_000.0,
    "Co": 50_000.0,
}
DEFAULT_REFERENCE_QTY = DEFAULT_REFERENCE_QTY_BY_METAL[DEFAULT_METAL]
DEFAULT_COBALT_MODE = "mid"
COBALT_MODES = ("mid", "max", "min")
COBALT_MODE_LABELS = {"mid": "Middle", "max": "Max", "min": "Min"}
VIEW_MODE = "country"
S7_VIEW_MODES = ("country", "chemistry", "chemistry_only")
EPSILON = 1e-9
GUEST_TOTAL_PATTERN = re.compile(r"<br>[0-9,]+(?:\.[0-9]+)? t$")
GUEST_INLINE_TOTAL_PATTERN = re.compile(r" \([0-9,]+(?:\.[0-9]+)? t\)")


def _normalize_template_label(raw: Any) -> str:
    text = str(raw or "")
    if "<br>" in text:
        text = text.split("<br>", 1)[0]
    text = re.sub(r" \([A-Z]{3}\)$", "", text)
    return text.strip()


def _hex_to_rgba(hex_value: str, opacity: float = 0.34) -> str:
    value = hex_value.lstrip("#")
    if len(value) != 6:
        return f"rgba(139, 146, 154, {opacity})"
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


def _fallback_rgba(color: str, alpha: float = 0.34) -> str:
    if color.startswith("#"):
        return _hex_to_rgba(color, alpha)
    if color.startswith("rgba("):
        rgba = color.removeprefix("rgba(").removesuffix(")").split(",")
        if len(rgba) == 4:
            return f"rgba({rgba[0].strip()}, {rgba[1].strip()}, {rgba[2].strip()}, {alpha})"
    return f"rgba(139, 146, 154, {alpha})"


def _is_special(row: dict[str, Any]) -> bool:
    return str(row.get("kind", "regular")) != "regular"


def _fallback_node_color(row: dict[str, Any]) -> str:
    if bool(row.get("is_non_source")):
        return SPECIAL_COLORS["non_source"]
    if bool(row.get("is_non_target")):
        return SPECIAL_COLORS["non_target"]
    if bool(row.get("is_unknown")):
        key = "unknown_source" if "source" in str(row.get("label", "")).lower() else "unknown_target"
        return SPECIAL_COLORS.get(key, SPECIAL_COLORS["unknown_source"])
    if bool(row.get("is_structural_sink")):
        label = str(row.get("label", "")).lower()
        if "refining other" in label:
            return SPECIAL_COLORS["refining_other"]
        return SPECIAL_COLORS["processing_unrelated"]
    region = str(row.get("region") or "Unknown")
    return REGION_COLORS.get(region, REGION_COLORS["Unknown"])


def _node_kind(row: dict[str, Any]) -> str:
    kind = str(row.get("kind", "regular"))
    if kind in {"regular", "aggregate", "source_special", "sink_special"}:
        return kind
    label = str(row.get("label", "")).lower()
    if bool(row.get("is_non_source")):
        return "source_special"
    if bool(row.get("is_unknown")) and "source" in label:
        return "source_special"
    if bool(row.get("is_non_target")) or bool(row.get("is_structural_sink")):
        return "sink_special"
    if bool(row.get("is_unknown")):
        return "sink_special"
    return "regular"


def _country_id_from_node_key(key: Any) -> int | None:
    match = re.search(r":(?:country|chem):(\d+)(?::|$)", str(key or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _node_region(repo: OutputRepository, row: dict[str, Any]) -> str:
    region = str(row.get("region") or "").strip()
    if region and region != "Unknown":
        return region
    country_id = _country_id_from_node_key(row.get("key"))
    if country_id is None:
        return "Unknown"
    return repo.country_region_by_id.get(country_id, "Unknown")


def _guest_hover_text(text: Any) -> str:
    cleaned = str(text or "")
    cleaned = GUEST_TOTAL_PATTERN.sub("", cleaned)
    cleaned = GUEST_INLINE_TOTAL_PATTERN.sub("", cleaned)
    return cleaned


def _apply_guest_figure_redaction(figure: dict[str, Any]) -> dict[str, Any]:
    if not figure.get("data"):
        return figure
    redacted = deepcopy(figure)
    trace = redacted["data"][0]
    node_data = trace.get("node", {})
    link_data = trace.get("link", {})
    customdata = node_data.get("customdata") or []
    node_data["customdata"] = [_guest_hover_text(value) for value in customdata]
    node_labels = node_data.get("label") or []
    source_indexes = link_data.get("source") or []
    target_indexes = link_data.get("target") or []
    link_data["customdata"] = [
        f"Source: {node_labels[int(source)]}<br>Target: {node_labels[int(target)]}"
        for source, target in zip(source_indexes, target_indexes)
    ]
    link_data["hovertemplate"] = "%{customdata}<extra></extra>"
    return redacted


def _rows_to_specs(
    repo: OutputRepository,
    ordered_nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    style_template: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, NodeSpec], list[LinkSpec]]:
    node_specs: dict[str, NodeSpec] = {}
    for row in ordered_nodes:
        key = str(row["key"])
        stage = str(row["stage"])
        label = str(row["label"])
        region = _node_region(repo, row)
        row["region"] = region
        template = style_template.get((stage, label))
        color = str(template["color"]) if template else str(row.get("color") or _fallback_node_color(row))
        node_specs[key] = NodeSpec(
            key=key,
            stage=stage,
            label=label,
            color=color,
            kind=_node_kind(row),
            hover=label,
            region=region,
        )

    link_specs: list[LinkSpec] = []
    for row in links:
        source = str(row["source"])
        target = str(row["target"])
        if source not in node_specs or target not in node_specs:
            continue
        link_specs.append(
            LinkSpec(
                source=source,
                target=target,
                value=float(row["value"]),
                color=_fallback_rgba(node_specs[source].color, 0.34),
            )
        )
    return node_specs, link_specs


def _style_template(
    repo: OutputRepository,
    metal: str,
    year: int,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
) -> tuple[dict[str, Any], dict[str, Any], dict[tuple[str, str], dict[str, Any]], dict[str, list[float]], dict[str, float], dict[str, Any]]:
    payload = repo.load_case_json(metal, year, "baseline", "payload", cobalt_mode)
    figure = payload["figure"]
    trace = figure["data"][0]
    node_x = [float(value) for value in trace["node"]["x"]]
    node_y = [float(value) for value in trace["node"]["y"]]
    node_color = list(trace["node"]["color"])
    node_custom = trace["node"].get("customdata") or trace["node"].get("label") or []
    unique_x = sorted({round(value, 6) for value in node_x})
    stage_lookup = {
        value: STAGE_ORDER[min(index, len(STAGE_ORDER) - 1)]
        for index, value in enumerate(unique_x)
    }

    style_by_stage_label: dict[tuple[str, str], dict[str, Any]] = {}
    stage_slots: dict[str, list[float]] = {stage: [] for stage in STAGE_ORDER}
    stage_x_map: dict[str, float] = {}
    for index, raw_label in enumerate(node_custom):
        stage = stage_lookup[round(node_x[index], 6)]
        label = _normalize_template_label(raw_label)
        stage_x_map.setdefault(stage, node_x[index])
        stage_slots.setdefault(stage, []).append(node_y[index])
        if label:
            style_by_stage_label[(stage, label)] = {
                "x": node_x[index],
                "y": node_y[index],
                "color": node_color[index],
            }

    for stage in stage_slots:
        stage_slots[stage] = sorted(float(value) for value in stage_slots[stage])

    return figure["layout"], trace, style_by_stage_label, stage_slots, stage_x_map, payload


def _resolved_table_view(scenario: str, table_view: str) -> str:
    return scenario if table_view == "auto" else table_view


def default_reference_quantity_for_metal(metal: str) -> float:
    return float(DEFAULT_REFERENCE_QTY_BY_METAL.get(metal, DEFAULT_REFERENCE_QTY))


def _uses_default_layout(
    sort_modes: dict[str, str] | None,
    stage_orders: dict[str, list[str]] | None,
    special_positions: dict[str, str] | None,
    aggregate_counts: dict[str, int] | None,
) -> bool:
    return not any((sort_modes or {}, stage_orders or {}, special_positions or {}, aggregate_counts or {}))


def _reference_qty_matches_default(metal: str, reference_qty: float | None) -> bool:
    if reference_qty is None:
        return True
    return abs(float(reference_qty) - default_reference_quantity_for_metal(metal)) <= EPSILON


def _cacheable_table_view(table_view: str) -> str:
    return table_view if table_view in {"auto", "compare", "baseline", "optimized"} else "auto"


def _resolve_s7_view_mode(s7_view_mode: str | None) -> str:
    normalized = str(s7_view_mode or VIEW_MODE).strip().lower().replace("-", "_")
    if normalized not in S7_VIEW_MODES:
        raise ValueError(f"Unsupported S7 view mode: {s7_view_mode}")
    return normalized


def _map_int_float(raw: dict[str, Any] | None) -> dict[int, float]:
    return {
        int(key): float(value)
        for key, value in (raw or {}).items()
    }


def _trade_rows(flow_type: type, rows: list[dict[str, Any]] | None) -> tuple[Any, ...]:
    return tuple(
        flow_type(
            exporter=int(item["exporter"]),
            importer=int(item["importer"]),
            value=float(item["value"]),
        )
        for item in (rows or [])
    )


def _nickel_inputs_from_raw(raw: dict[str, Any]) -> NickelYearInputs:
    return NickelYearInputs(
        mining_total=_map_int_float(raw.get("mining_total")),
        mining_battery=_map_int_float(raw.get("mining_battery")),
        mining_unrelated=_map_int_float(raw.get("mining_unrelated")),
        mining_concentrate=_map_int_float(raw.get("mining_concentrate")),
        processing_total=_map_int_float(raw.get("processing_total")),
        processing_battery=_map_int_float(raw.get("processing_battery")),
        processing_unrelated=_map_int_float(raw.get("processing_unrelated")),
        processing_balance=_map_int_float(raw.get("processing_balance")),
        refining_total=_map_int_float(raw.get("refining_total")),
        refining_balance=_map_int_float(raw.get("refining_balance")),
        cathode_total=_map_int_float(raw.get("cathode_total")),
        cathode_ncm=_map_int_float(raw.get("cathode_ncm")),
        cathode_nca=_map_int_float(raw.get("cathode_nca")),
        cathode_balance=_map_int_float(raw.get("cathode_balance")),
        cathode_ncm_balance=_map_int_float(raw.get("cathode_ncm_balance")),
        cathode_nca_balance=_map_int_float(raw.get("cathode_nca_balance")),
        trade1=_trade_rows(NickelTradeFlow, raw.get("trade1")),
        trade2=_trade_rows(NickelTradeFlow, raw.get("trade2")),
        trade3=_trade_rows(NickelTradeFlow, raw.get("trade3")),
    )


def _lithium_inputs_from_raw(raw: dict[str, Any]) -> LithiumYearInputs:
    return LithiumYearInputs(
        mining_total=_map_int_float(raw.get("mining_total")),
        mining_brine=_map_int_float(raw.get("mining_brine")),
        mining_lithium_ores=_map_int_float(raw.get("mining_lithium_ores")),
        processing_total=_map_int_float(raw.get("processing_total")),
        processing_battery=_map_int_float(raw.get("processing_battery")),
        processing_unrelated=_map_int_float(raw.get("processing_unrelated")),
        processing_brine_total=_map_int_float(raw.get("processing_brine_total")),
        processing_lithium_ores_total=_map_int_float(raw.get("processing_lithium_ores_total")),
        processing_brine_balance=_map_int_float(raw.get("processing_brine_balance")),
        processing_lithium_ores_balance=_map_int_float(raw.get("processing_lithium_ores_balance")),
        refining_total=_map_int_float(raw.get("refining_total")),
        refining_hydroxide=_map_int_float(raw.get("refining_hydroxide")),
        refining_carbonate=_map_int_float(raw.get("refining_carbonate")),
        refining_hydroxide_balance=_map_int_float(raw.get("refining_hydroxide_balance")),
        refining_carbonate_balance=_map_int_float(raw.get("refining_carbonate_balance")),
        cathode_total=_map_int_float(raw.get("cathode_total")),
        cathode_ncm=_map_int_float(raw.get("cathode_ncm")),
        cathode_nca=_map_int_float(raw.get("cathode_nca")),
        cathode_lfp=_map_int_float(raw.get("cathode_lfp")),
        cathode_ncm_nca_balance=_map_int_float(raw.get("cathode_ncm_nca_balance")),
        cathode_ncm_balance=_map_int_float(raw.get("cathode_ncm_balance")),
        cathode_nca_balance=_map_int_float(raw.get("cathode_nca_balance")),
        cathode_lfp_balance=_map_int_float(raw.get("cathode_lfp_balance")),
        trade1=_trade_rows(LithiumTradeFlow, raw.get("trade1")),
        trade2=_trade_rows(LithiumTradeFlow, raw.get("trade2")),
        trade3_hydroxide=_trade_rows(LithiumTradeFlow, raw.get("trade3_hydroxide")),
        trade3_carbonate=_trade_rows(LithiumTradeFlow, raw.get("trade3_carbonate")),
    )


def _cobalt_inputs_from_raw(raw: dict[str, Any]) -> CobaltYearInputs:
    return CobaltYearInputs(
        mining_total=_map_int_float(raw.get("mining_total")),
        mining_battery=_map_int_float(raw.get("mining_battery")),
        mining_concentrate=_map_int_float(raw.get("mining_concentrate")),
        mining_sulphate=_map_int_float(raw.get("mining_sulphate")),
        processing_total=_map_int_float(raw.get("processing_total")),
        processing_unrelated=_map_int_float(raw.get("processing_unrelated")),
        refining_max=_map_int_float(raw.get("refining_max")),
        refining_mid=_map_int_float(raw.get("refining_mid")),
        refining_min=_map_int_float(raw.get("refining_min")),
        refining_max_balance=_map_int_float(raw.get("refining_max_balance")),
        refining_mid_balance=_map_int_float(raw.get("refining_mid_balance")),
        refining_min_balance=_map_int_float(raw.get("refining_min_balance")),
        cathode_total=_map_int_float(raw.get("cathode_total")),
        cathode_ncm=_map_int_float(raw.get("cathode_ncm")),
        cathode_nca=_map_int_float(raw.get("cathode_nca")),
        cathode_max_total_balance=_map_int_float(raw.get("cathode_max_total_balance")),
        cathode_mid_total_balance=_map_int_float(raw.get("cathode_mid_total_balance")),
        cathode_min_total_balance=_map_int_float(raw.get("cathode_min_total_balance")),
        cathode_max_ncm_balance=_map_int_float(raw.get("cathode_max_ncm_balance")),
        cathode_mid_ncm_balance=_map_int_float(raw.get("cathode_mid_ncm_balance")),
        cathode_min_ncm_balance=_map_int_float(raw.get("cathode_min_ncm_balance")),
        cathode_max_nca_balance=_map_int_float(raw.get("cathode_max_nca_balance")),
        cathode_mid_nca_balance=_map_int_float(raw.get("cathode_mid_nca_balance")),
        cathode_min_nca_balance=_map_int_float(raw.get("cathode_min_nca_balance")),
        trade1=_trade_rows(CobaltTradeFlow, raw.get("trade1")),
        trade2=_trade_rows(CobaltTradeFlow, raw.get("trade2")),
        trade3=_trade_rows(CobaltTradeFlow, raw.get("trade3")),
    )


def _build_s7_graph_from_inputs(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    cobalt_mode: str,
    s7_view_mode: str,
    aggregate_nmc_nca: bool,
) -> tuple[dict[str, NodeSpec], list[LinkSpec]]:
    raw = repo.load_case_json(metal, year, scenario, "inputs", cobalt_mode)
    aggregate_display = s7_view_mode == "chemistry_only"
    if metal == "Ni":
        return nickel_sankey._build_chemistry_payload(
            _nickel_inputs_from_raw(raw),
            aggregate_display=aggregate_display,
            aggregate_nmc_nca=aggregate_nmc_nca,
        )
    if metal == "Li":
        return lithium_sankey._build_chemistry_payload(
            _lithium_inputs_from_raw(raw),
            aggregate_display=aggregate_display,
            aggregate_nmc_nca=aggregate_nmc_nca,
        )
    if metal == "Co":
        return cobalt_sankey._build_chemistry_payload(
            _cobalt_inputs_from_raw(raw),
            cobalt_mode=cobalt_mode,
            aggregate_display=aggregate_display,
            aggregate_nmc_nca=aggregate_nmc_nca,
        )
    raise ValueError(f"Unsupported metal for S7 chemistry view: {metal}")


def _case_rows_for_s7_view(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    cobalt_mode: str,
    s7_view_mode: str,
    aggregate_nmc_nca: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if s7_view_mode == VIEW_MODE and not aggregate_nmc_nca:
        return (
            repo.load_case_csv(metal, year, scenario, "nodes", cobalt_mode).to_dict(orient="records"),
            repo.load_case_csv(metal, year, scenario, "links", cobalt_mode).to_dict(orient="records"),
        )
    nodes, links = _build_s7_graph_from_inputs(
        repo,
        metal,
        year,
        scenario,
        cobalt_mode,
        s7_view_mode,
        aggregate_nmc_nca,
    )
    node_rows = pipeline_v1.node_records(nodes, links, metal, year, scenario)
    for row in node_rows:
        spec = nodes.get(str(row.get("key")))
        if spec:
            row["color"] = spec.color
    return (
        node_rows,
        pipeline_v1.link_records(nodes, links, metal, year, scenario),
    )


def _manual_sort(rows: list[dict[str, Any]], manual_order: list[str]) -> list[dict[str, Any]]:
    by_label = {str(row["label"]): row for row in rows}
    ordered = [by_label[label] for label in manual_order if label in by_label]
    remaining = [row for row in rows if str(row["label"]) not in manual_order]
    remaining.sort(key=lambda row: (-float(row["value"]), str(row["label"])))
    return ordered + remaining


def _stage_sort(
    stage: str,
    rows: list[dict[str, Any]],
    sort_mode: str,
    manual_order: list[str],
) -> list[dict[str, Any]]:
    del stage
    if sort_mode == "manual":
        return _manual_sort(rows, manual_order)
    if sort_mode == "continent":
        return sorted(
            rows,
            key=lambda row: (
                REGION_ORDER.index(str(row.get("region") or "Unknown"))
                if str(row.get("region") or "Unknown") in REGION_ORDER
                else len(REGION_ORDER),
                -float(row["value"]),
                str(row["label"]),
            ),
        )
    return sorted(rows, key=lambda row: (-float(row["value"]), str(row["label"])))


def _stage_positions(stage: str, count: int, slots: dict[str, list[float]]) -> list[float]:
    stage_slots = list(slots.get(stage, []))
    if count <= 0:
        return []
    if len(stage_slots) == count:
        return stage_slots
    if len(stage_slots) >= 2:
        start = min(stage_slots)
        end = max(stage_slots)
    else:
        start, end = 0.05, 0.95
    if count == 1:
        return [round((start + end) / 2.0, 6)]
    step = (end - start) / max(count - 1, 1)
    return [round(start + step * index, 6) for index in range(count)]


def _prune_zero_rows(
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    epsilon: float = EPSILON,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid_keys = {str(row["key"]) for row in nodes}
    pruned_links = [
        row
        for row in links
        if str(row.get("source")) in valid_keys
        and str(row.get("target")) in valid_keys
        and abs(float(row.get("value", 0.0) or 0.0)) > epsilon
    ]
    incoming: dict[str, float] = {}
    outgoing: dict[str, float] = {}
    for row in pruned_links:
        value = float(row["value"])
        source = str(row["source"])
        target = str(row["target"])
        outgoing[source] = outgoing.get(source, 0.0) + value
        incoming[target] = incoming.get(target, 0.0) + value

    pruned_nodes = [
        row
        for row in nodes
        if max(
            abs(float(row.get("value", 0.0) or 0.0)),
            incoming.get(str(row["key"]), 0.0),
            outgoing.get(str(row["key"]), 0.0),
        )
        > epsilon
    ]
    allowed_keys = {str(row["key"]) for row in pruned_nodes}
    pruned_links = [
        row
        for row in pruned_links
        if str(row["source"]) in allowed_keys and str(row["target"]) in allowed_keys
    ]
    return pruned_nodes, pruned_links


def _ordered_stage_rows(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    aggregate_counts: dict[str, int] | None = None,
    nodes: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, str], dict[str, str]]:
    _, _, style_template, _, _, baseline_payload = _style_template(repo, metal, year)
    nodes = list(nodes) if nodes is not None else repo.load_case_csv(metal, year, scenario, "nodes").to_dict(orient="records")

    ordered_nodes: list[dict[str, Any]] = []
    stage_controls: dict[str, Any] = {}
    resolved_sort_modes: dict[str, str] = {}
    resolved_special_positions: dict[str, str] = {}
    baseline_stage_controls = baseline_payload.get("stageControls", {})
    baseline_special_positions = baseline_payload.get("specialPositions", {})

    for stage in STAGE_ORDER:
        stage_rows = [row for row in nodes if str(row["stage"]) == stage]
        regular_rows = [row for row in stage_rows if not _is_special(row)]
        special_rows = [row for row in stage_rows if _is_special(row)]
        default_sort_mode = str(baseline_stage_controls.get(stage, {}).get("sortMode", "size"))
        sort_mode = sort_modes.get(stage, default_sort_mode)
        resolved_sort_modes[stage] = sort_mode
        special_position = special_positions.get(stage, baseline_special_positions.get(stage, DEFAULT_SPECIAL_POSITION))
        resolved_special_positions[stage] = special_position

        for row in regular_rows:
            row["region"] = _node_region(repo, row)

        size_rank_by_key = {
            str(row["key"]): index
            for index, row in enumerate(
                sorted(regular_rows, key=lambda item: (-float(item["value"]), str(item["label"]))),
                start=1,
            )
        }

        ordered_regular = _stage_sort(stage, regular_rows, sort_mode, stage_orders.get(stage, []))
        ordered_special = sorted(
            special_rows,
            key=lambda row: (
                0 if (stage, str(row["label"])) in style_template else 1,
                style_template.get((stage, str(row["label"])), {}).get("y", 1.0),
                -float(row["value"]),
            ),
        )
        combined = ordered_special + ordered_regular if special_position == "first" else ordered_regular + ordered_special
        ordered_nodes.extend(combined)

        if sort_mode == "manual":
            display_items = _manual_sort(regular_rows, stage_orders.get(stage, []))
        elif sort_mode == "continent":
            display_items = _stage_sort(stage, regular_rows, sort_mode, [])
        else:
            display_items = _stage_sort(stage, regular_rows, "size", [])

        stage_controls[stage] = {
            "label": STAGE_LABELS[stage],
            "sortMode": sort_mode,
            "specialPosition": special_position,
            "hasSpecialNodes": bool(ordered_special),
            "specialNodeCount": len(ordered_special),
            "aggregateCount": int((aggregate_counts or {}).get(stage, 0) or 0) if sort_mode != "continent" else 0,
            "maxAggregateCount": max(len(regular_rows) - 1, 0),
            "items": [
                {
                    "label": str(row["label"]),
                    "value": float(row["value"]),
                    "rank": size_rank_by_key.get(str(row["key"])),
                    "group": str(row.get("region") or "Unknown"),
                    "groupColor": REGION_COLORS.get(str(row.get("region") or "Unknown"), REGION_COLORS["Unknown"]),
                }
                for row in display_items
            ],
        }

    return ordered_nodes, stage_controls, resolved_sort_modes, resolved_special_positions


def _build_stage_summary(repo: OutputRepository, metal: str, year: int, scenario: str, cobalt_mode: str = DEFAULT_COBALT_MODE) -> list[dict[str, Any]]:
    raw_nodes = repo.load_case_csv(metal, year, scenario, "nodes", cobalt_mode).to_dict(orient="records")
    raw_links = repo.load_case_csv(metal, year, scenario, "links", cobalt_mode).to_dict(orient="records")
    nodes, _links = _prune_zero_rows(raw_nodes, raw_links)
    node_counts: dict[str, int] = {}
    for row in nodes:
        stage = str(row["stage"])
        node_counts[stage] = node_counts.get(stage, 0) + 1
    rows = repo.get_stage_rows(metal, year, scenario, cobalt_mode)
    return [
        {
            "id": row["stage"],
            "label": STAGE_LABELS.get(row["stage"], row["stage"]),
            "nodeCount": int(node_counts.get(row["stage"], 0)),
            "total": float(row.get("total_value", 0.0)),
        }
        for row in rows
    ]


def _build_stage_summary_for_view(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    cobalt_mode: str,
    s7_view_mode: str,
    s7_aggregate_nmc_nca: bool,
) -> list[dict[str, Any]]:
    if s7_view_mode == VIEW_MODE and not s7_aggregate_nmc_nca:
        return _build_stage_summary(repo, metal, year, scenario, cobalt_mode)
    raw_nodes, raw_links = _case_rows_for_s7_view(
        repo,
        metal,
        year,
        scenario,
        cobalt_mode,
        s7_view_mode,
        s7_aggregate_nmc_nca,
    )
    nodes, _links = _prune_zero_rows(raw_nodes, raw_links)
    node_counts: dict[str, int] = {}
    totals: dict[str, float] = {}
    for row in nodes:
        stage = str(row["stage"])
        node_counts[stage] = node_counts.get(stage, 0) + 1
        totals[stage] = totals.get(stage, 0.0) + float(row.get("value", 0.0) or 0.0)
    return [
        {
            "id": stage,
            "label": STAGE_LABELS.get(stage, stage),
            "nodeCount": int(node_counts.get(stage, 0)),
            "total": float(totals.get(stage, 0.0)),
        }
        for stage in STAGE_ORDER
        if stage in node_counts
    ]


def _dataset_status(repo: OutputRepository, metal: str, year: int, scenario: str, table_view: str, cobalt_mode: str = DEFAULT_COBALT_MODE) -> dict[str, dict[str, Any]]:
    resolved_table = _resolved_table_view(scenario, table_view)
    baseline_case = repo.case_dir(metal, year, "baseline")
    first_optimization_case = repo.case_dir(metal, year, "first_optimization")
    comparison_dir = repo.scenario_comparison_dirs.get(scenario, repo.comparison_dir)
    suffix = f" ({COBALT_MODE_LABELS.get(cobalt_mode, cobalt_mode)})" if metal == "Co" else ""
    payload = {
        f"Current Result Folder{suffix}": {"exists": True, "label": repo.case_dir(metal, year, scenario).name},
        f"Original Export{suffix}": {"exists": baseline_case.exists(), "label": baseline_case.name},
        f"First Optimization Export{suffix}": {"exists": first_optimization_case.exists(), "label": first_optimization_case.name},
        "Comparison Tables": {"exists": comparison_dir.exists(), "label": comparison_dir.name},
        "Table Source": {"exists": True, "label": TABLE_VIEW_LABELS.get(resolved_table, resolved_table)},
    }
    return payload


def _node_value_map(nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> dict[str, float]:
    incoming: dict[str, float] = {}
    outgoing: dict[str, float] = {}
    for link in links:
        value = float(link["value"])
        incoming[str(link["target"])] = incoming.get(str(link["target"]), 0.0) + value
        outgoing[str(link["source"])] = outgoing.get(str(link["source"]), 0.0) + value
    values: dict[str, float] = {}
    for row in nodes:
        key = str(row["key"])
        values[key] = max(float(row.get("value", 0.0)), incoming.get(key, 0.0), outgoing.get(key, 0.0))
    return values


def _px_per_unit_from_reference(reference_qty: float) -> float:
    safe_qty = max(float(reference_qty), 1.0)
    return REFERENCE_NODE_HEIGHT_PX / safe_qty


def _layout_from_reference(
    ordered_nodes: list[dict[str, Any]],
    values: dict[str, float],
    reference_qty: float,
) -> tuple[list[float], list[float], int, float]:
    px_per_unit = _px_per_unit_from_reference(reference_qty)
    stage_stack_heights: dict[str, float] = {}
    node_heights: dict[str, float] = {}
    nodes_by_stage: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGE_ORDER}
    for row in ordered_nodes:
        nodes_by_stage.setdefault(str(row["stage"]), []).append(row)

    for stage in STAGE_ORDER:
        total_height = 0.0
        stage_rows = nodes_by_stage.get(stage, [])
        for index, row in enumerate(stage_rows):
            key = str(row["key"])
            height = values.get(key, 0.0) * px_per_unit
            node_heights[key] = height
            total_height += height
            if index < len(stage_rows) - 1:
                total_height += GAP_PX
        stage_stack_heights[stage] = total_height

    plot_height = max(
        max(stage_stack_heights.values(), default=0.0),
        float(MIN_STAGE_HEIGHT_PX - TOP_BAND_PX - BOTTOM_BAND_PX),
    )
    figure_height = int(max(MIN_STAGE_HEIGHT_PX, plot_height + TOP_BAND_PX + BOTTOM_BAND_PX))
    plot_height = float(figure_height - TOP_BAND_PX - BOTTOM_BAND_PX)

    x_positions: list[float] = []
    y_positions: list[float] = []
    for stage in STAGE_ORDER:
        current_y = 0.0
        for row in nodes_by_stage.get(stage, []):
            key = str(row["key"])
            x_positions.append(X_MAP[stage])
            center_y = current_y + (node_heights.get(key, 0.0) / 2.0)
            y_positions.append(center_y / plot_height if plot_height > EPSILON else 0.0)
            current_y += node_heights.get(key, 0.0) + GAP_PX
    tallest_stage_content = max(stage_stack_heights.values(), default=0.0)
    return x_positions, y_positions, figure_height, tallest_stage_content


def build_figure(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    theme: str,
    reference_qty: float,
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    aggregate_counts: dict[str, int] | None = None,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
    access_mode: str = "analyst",
    s7_view_mode: str = VIEW_MODE,
    s7_aggregate_nmc_nca: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, str], dict[str, int]]:
    resolved_s7_view_mode = _resolve_s7_view_mode(s7_view_mode)
    resolved_s7_aggregate = bool(s7_aggregate_nmc_nca and resolved_s7_view_mode != VIEW_MODE)
    _, _, style_template, _, _, _ = _style_template(repo, metal, year, cobalt_mode)
    raw_nodes, raw_links = _case_rows_for_s7_view(
        repo,
        metal,
        year,
        scenario,
        cobalt_mode,
        resolved_s7_view_mode,
        resolved_s7_aggregate,
    )
    visible_nodes, visible_links = _prune_zero_rows(raw_nodes, raw_links)
    ordered_nodes, _stage_controls_seed, resolved_sort_modes, resolved_special_positions = _ordered_stage_rows(
        repo,
        metal,
        year,
        scenario,
        sort_modes,
        stage_orders,
        special_positions,
        aggregate_counts,
        nodes=visible_nodes,
    )
    node_specs, link_specs = _rows_to_specs(repo, ordered_nodes, visible_links, style_template)
    resolved_aggregate_counts = _shared_validate_aggregate_counts(
        node_specs,
        link_specs,
        resolved_sort_modes,
        stage_orders,
        resolved_special_positions,
        aggregate_counts,
    )
    figure_nodes, figure_links = _shared_apply_stage_aggregation(
        node_specs,
        link_specs,
        resolved_sort_modes,
        stage_orders,
        resolved_special_positions,
        resolved_aggregate_counts,
        resolved_s7_view_mode,
        EPSILON,
    )
    stage_controls = deepcopy(_stage_controls_seed)
    for stage in STAGE_ORDER:
        if stage in stage_controls:
            stage_controls[stage]["aggregateCount"] = (
                resolved_aggregate_counts.get(stage, 0) if resolved_sort_modes.get(stage) != "continent" else 0
            )
    figure_payload = _shared_build_figure(
        figure_nodes,
        figure_links,
        year,
        resolved_s7_view_mode,
        reference_qty,
        resolved_sort_modes,
        stage_orders,
        resolved_special_positions,
        metal,
        theme,
        EPSILON,
    )
    if access_mode == "guest":
        figure_payload = _apply_guest_figure_redaction(figure_payload)
    return figure_payload, stage_controls, resolved_sort_modes, resolved_special_positions, resolved_aggregate_counts


def _apply_access_mode(payload: dict[str, Any], access_mode: str) -> dict[str, Any]:
    payload["accessMode"] = access_mode
    if access_mode != "guest":
        return payload
    payload["stageSummary"] = []
    payload["comparison"] = {}
    payload["tables"] = {
        "metrics": [],
        "stages": [],
        "parameters": [],
        "metricsActive": [],
        "stagesActive": [],
        "parametersActive": [],
        "producerCoefficients": [],
        "transitions": [],
        "unknownBreakdown": [],
        "tradeFlows": [],
        "activeTableView": "guest",
        "transitionNote": "Diagnostics are hidden in guest mode.",
    }
    for stage in payload.get("stageControls", {}).values():
        for item in stage.get("items", []):
            item["value"] = None
    return payload


def _build_app_payload_uncached(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    table_view: str,
    reference_qty: float | None = DEFAULT_REFERENCE_QTY,
    theme: str = DEFAULT_THEME,
    sort_modes: dict[str, str] | None = None,
    stage_orders: dict[str, list[str]] | None = None,
    special_positions: dict[str, str] | None = None,
    aggregate_counts: dict[str, int] | None = None,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
    access_mode: str = "analyst",
    s7_view_mode: str = VIEW_MODE,
    s7_aggregate_nmc_nca: bool = False,
) -> dict[str, Any]:
    sort_modes = sort_modes or {}
    stage_orders = stage_orders or {}
    special_positions = special_positions or {}
    aggregate_counts = aggregate_counts or {}
    theme = theme if theme in THEME_MODES else DEFAULT_THEME
    if reference_qty is None:
        reference_qty = default_reference_quantity_for_metal(metal)
    if reference_qty <= 0:
        raise ValueError("reference_qty must be greater than 0.")
    resolved_s7_view_mode = _resolve_s7_view_mode(s7_view_mode)
    resolved_s7_aggregate = bool(s7_aggregate_nmc_nca and resolved_s7_view_mode != VIEW_MODE)
    comparison = repo.get_comparison_row(metal, year, scenario, cobalt_mode) if scenario != "baseline" else {}
    figure, stage_controls, resolved_sort_modes, resolved_special_positions, resolved_aggregate_counts = build_figure(
        repo,
        metal,
        year,
        scenario,
        theme,
        reference_qty,
        sort_modes,
        stage_orders,
        special_positions,
        aggregate_counts,
        cobalt_mode,
        access_mode,
        resolved_s7_view_mode,
        resolved_s7_aggregate,
    )
    resolved_table_view = _resolved_table_view(scenario, table_view)
    stage_summary = _build_stage_summary_for_view(
        repo,
        metal,
        year,
        scenario,
        cobalt_mode,
        resolved_s7_view_mode,
        resolved_s7_aggregate,
    )
    dataset_status = _dataset_status(repo, metal, year, scenario, table_view, cobalt_mode)

    compare_mode = "compare" if scenario != "baseline" else "baseline"
    transition_note = (
        "Original-only diagnostics are shown in this mode. Stage-level optimization diagnostics appear when you switch to First Optimization."
        if scenario == "baseline"
        else (
            "First Optimization now renders the latest conversion_factor_optimization result after synchronizing it into the published runtime snapshot. The non-guest tables below Sorting Studio summarize stage outcomes, bounds, special handling, source scaling, and c_pp / c_pn / c_np coefficients."
            if scenario == "first_optimization"
            else "Diagnostics summarize the selected optimization output."
        )
    )

    payload = {
        "metal": metal,
        "theme": theme,
        "year": year,
        "viewMode": resolved_s7_view_mode,
        "s7ViewMode": resolved_s7_view_mode,
        "s7AggregateNmcNca": resolved_s7_aggregate,
        "cobaltMode": cobalt_mode,
        "resultMode": scenario,
        "resultModeLabel": SCENARIO_LABELS.get(scenario, scenario),
        "tableView": resolved_table_view,
        "tableViewLabel": TABLE_VIEW_LABELS.get(resolved_table_view, resolved_table_view),
        "referenceQuantity": reference_qty,
        "aggregateCounts": resolved_aggregate_counts,
        "specialPositions": resolved_special_positions,
        "sortModes": resolved_sort_modes,
        "figure": figure,
        "stageSummary": stage_summary,
        "stageControls": stage_controls,
        "datasetStatus": dataset_status,
        "notes": repo.build_case_notes(metal, scenario, table_view, cobalt_mode),
        "comparison": comparison,
        "tables": {
            "metrics": repo.build_metric_rows(metal, year, scenario, compare_mode, cobalt_mode),
            "stages": repo.build_stage_rows(metal, year, scenario, compare_mode, cobalt_mode),
            "parameters": repo.build_parameter_rows(metal, scenario, compare_mode, cobalt_mode, year),
            "metricsActive": repo.build_metric_rows(metal, year, scenario, table_view, cobalt_mode),
            "stagesActive": repo.build_stage_rows(metal, year, scenario, table_view, cobalt_mode),
            "parametersActive": repo.build_parameter_rows(metal, scenario, table_view, cobalt_mode, year),
            "producerCoefficients": repo.get_producer_coefficient_rows(metal, year, scenario, cobalt_mode),
            "transitions": repo.get_transition_rows(metal, year, scenario, cobalt_mode),
            "unknownBreakdown": repo.get_unknown_breakdown_rows(metal, year, scenario, cobalt_mode),
            "tradeFlows": repo.get_trade_flow_compare_rows(metal, year, scenario, cobalt_mode),
            "activeTableView": resolved_table_view,
            "transitionNote": transition_note,
        },
    }
    return _apply_access_mode(payload, access_mode)


@lru_cache(maxsize=512)
def _build_default_payload_cached(
    metal: str,
    year: int,
    scenario: str,
    table_view: str,
    reference_qty: float,
    theme: str,
    cobalt_mode: str,
    access_mode: str,
) -> dict[str, Any]:
    repo = get_repository()
    return _build_app_payload_uncached(
        repo,
        metal,
        year,
        scenario,
        table_view,
        reference_qty=reference_qty,
        theme=theme,
        sort_modes={},
        stage_orders={},
        special_positions={},
        aggregate_counts={},
        cobalt_mode=cobalt_mode,
        access_mode=access_mode,
    )


def clear_default_payload_cache() -> None:
    _build_default_payload_cached.cache_clear()


def default_payload_cache_info() -> dict[str, int]:
    info = _build_default_payload_cached.cache_info()
    return {
        "hits": int(info.hits),
        "misses": int(info.misses),
        "maxsize": int(info.maxsize or 0),
        "currsize": int(info.currsize),
    }


def warm_default_payload_cache() -> dict[str, Any]:
    repo = get_repository()
    warmed = 0
    for metal in repo.metals:
        reference_qty = default_reference_quantity_for_metal(metal)
        cobalt_modes = COBALT_MODES if metal == "Co" else ("mid",)
        for year in repo.years:
            for scenario in RESULT_MODES:
                for theme in THEME_MODES:
                    for access_mode in ("guest", "analyst"):
                        for cobalt_mode in cobalt_modes:
                            _build_default_payload_cached(
                                metal,
                                year,
                                scenario,
                                "compare",
                                reference_qty,
                                theme,
                                cobalt_mode,
                                access_mode,
                            )
                            warmed += 1
    return {
        "warmedPayloads": warmed,
        "cache": default_payload_cache_info(),
    }


def build_app_payload(
    repo: OutputRepository,
    metal: str,
    year: int,
    scenario: str,
    table_view: str,
    reference_qty: float | None = DEFAULT_REFERENCE_QTY,
    theme: str = DEFAULT_THEME,
    sort_modes: dict[str, str] | None = None,
    stage_orders: dict[str, list[str]] | None = None,
    special_positions: dict[str, str] | None = None,
    aggregate_counts: dict[str, int] | None = None,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
    access_mode: str = "analyst",
    s7_view_mode: str = VIEW_MODE,
    s7_aggregate_nmc_nca: bool = False,
) -> dict[str, Any]:
    runtime_repo = get_repository()
    resolved_s7_view_mode = _resolve_s7_view_mode(s7_view_mode)
    resolved_s7_aggregate = bool(s7_aggregate_nmc_nca and resolved_s7_view_mode != VIEW_MODE)
    if (
        repo is runtime_repo
        and _uses_default_layout(sort_modes, stage_orders, special_positions, aggregate_counts)
        and _reference_qty_matches_default(metal, reference_qty)
        and resolved_s7_view_mode == VIEW_MODE
        and not resolved_s7_aggregate
    ):
        return deepcopy(
            _build_default_payload_cached(
                metal,
                year,
                scenario,
                _cacheable_table_view(table_view),
                default_reference_quantity_for_metal(metal),
                theme,
                cobalt_mode,
                access_mode,
            )
        )
    return _build_app_payload_uncached(
        repo,
        metal,
        year,
        scenario,
        table_view,
        reference_qty=reference_qty,
        theme=theme,
        sort_modes=sort_modes,
        stage_orders=stage_orders,
        special_positions=special_positions,
        aggregate_counts=aggregate_counts,
        cobalt_mode=cobalt_mode,
        access_mode=access_mode,
        s7_view_mode=resolved_s7_view_mode,
        s7_aggregate_nmc_nca=resolved_s7_aggregate,
    )
