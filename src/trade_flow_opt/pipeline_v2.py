from __future__ import annotations

import json
import shutil
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from trade_flow_opt import pipeline_v1 as v1


# Paths / 路径配置
PROJECT_ROOT = v1.PROJECT_ROOT
OUTPUT_ROOT = v1.OUTPUT_ROOT
BASELINE_OUTPUT_ROOT = v1.BASELINE_OUTPUT_ROOT
OPTIMIZED_OUTPUT_ROOT = v1.OPTIMIZED_OUTPUT_ROOT
COMPARISON_OUTPUT_ROOT = v1.COMPARISON_OUTPUT_ROOT
SPREADSHEET_OUTPUT_ROOT = v1.SPREADSHEET_OUTPUT_ROOT
VERSION_OUTPUT_ROOT = PROJECT_ROOT / "output_versions"
V1_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v1"
V2_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v2"

METALS = v1.METALS
YEARS = v1.YEARS
DEFAULT_COBALT_MODE = v1.DEFAULT_COBALT_MODE
EPSILON = v1.EPSILON

TransitionContext = v1.TransitionContext
EdgeMap = v1.EdgeMap


@dataclass(frozen=True)
class HyperParameters:
    mirror_weight: float
    lag_weight: float
    reexport_cap: float
    source_priority_count: int
    dual_priority_count: int
    source_alpha_lower: float
    source_alpha_upper: float
    dual_alpha_lower: float
    dual_alpha_upper: float
    alpha_step: float
    scale_passes: int
    deviation_weight: float
    non_source_weight: float
    non_target_weight: float
    max_residual_weight: float

    def values_for_role(self, role: str) -> list[float]:
        if role == "source":
            lower = self.source_alpha_lower
            upper = self.source_alpha_upper
        elif role == "dual":
            lower = self.dual_alpha_lower
            upper = self.dual_alpha_upper
        else:
            return [1.0]
        values: list[float] = []
        current = lower
        while current <= upper + 1e-9:
            values.append(round(current, 6))
            current += self.alpha_step
        if 1.0 not in values:
            values.append(1.0)
        return sorted(set(values))


HYPERPARAM_GRID = (
    HyperParameters(0.70, 0.00, 0.50, 6, 3, 0.75, 1.25, 0.85, 1.15, 0.10, 2, 0.10, 0.03, 0.03, 0.05),
    HyperParameters(0.70, 0.05, 0.60, 6, 3, 0.75, 1.25, 0.85, 1.15, 0.10, 2, 0.10, 0.03, 0.03, 0.05),
    HyperParameters(0.80, 0.05, 0.70, 8, 4, 0.70, 1.30, 0.80, 1.20, 0.10, 2, 0.12, 0.04, 0.04, 0.07),
    HyperParameters(0.80, 0.10, 0.70, 8, 4, 0.70, 1.30, 0.80, 1.20, 0.10, 2, 0.12, 0.04, 0.04, 0.07),
    HyperParameters(0.85, 0.10, 0.85, 10, 5, 0.65, 1.35, 0.75, 1.25, 0.10, 2, 0.15, 0.04, 0.04, 0.10),
)


def load_year_inputs(metal: str, year: int):
    return v1.load_year_inputs(metal, year)


def build_country_graph(metal: str, year: int, *, inputs=None, cobalt_mode: str = DEFAULT_COBALT_MODE):
    return v1.build_country_graph(metal, year, inputs=inputs, cobalt_mode=cobalt_mode)


def build_country_payload(metal: str, year: int, *, cobalt_mode: str = DEFAULT_COBALT_MODE) -> dict[str, Any]:
    return v1.build_country_payload(metal, year, cobalt_mode=cobalt_mode)


def serialize_inputs(inputs) -> dict[str, Any]:
    return v1.serialize_inputs(inputs)


def replace_trade_fields(metal: str, base_inputs, field_flow_maps: dict[str, EdgeMap]):
    return v1.replace_trade_fields(metal, base_inputs, field_flow_maps)


def summarize_graph(nodes: dict[str, Any], links: list[Any], metal: str, year: int, scenario: str):
    return v1.summarize_graph(nodes, links, metal, year, scenario)


def stage_summary(node_df: pd.DataFrame) -> pd.DataFrame:
    return v1.stage_summary(node_df)


def transition_contexts(metal: str, inputs, *, cobalt_mode: str = DEFAULT_COBALT_MODE) -> dict[str, TransitionContext]:
    return v1.transition_contexts(metal, inputs, cobalt_mode=cobalt_mode)


def _ensure_output_dirs() -> None:
    for path in (BASELINE_OUTPUT_ROOT, OPTIMIZED_OUTPUT_ROOT, COMPARISON_OUTPUT_ROOT, SPREADSHEET_OUTPUT_ROOT, VERSION_OUTPUT_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def _write_case_exports(root: Path, metal: str, year: int, scenario: str, inputs, nodes, links, extra_payload: dict[str, Any] | None = None):
    return v1._write_case_exports(root, metal, year, scenario, inputs, nodes, links, extra_payload)


def export_baseline() -> tuple[pd.DataFrame, pd.DataFrame]:
    return v1.export_baseline()


def _country_roles(context: TransitionContext) -> dict[int, str]:
    roles: dict[int, str] = {}
    countries = set(context.trade_supply) | set(context.target_totals) | set(context.source_totals) | set(context.direct_local)
    for country_id in countries:
        has_source = float(context.trade_supply.get(country_id, 0.0)) > EPSILON
        has_target = float(context.target_totals.get(country_id, 0.0)) > EPSILON
        if has_source and has_target:
            roles[int(country_id)] = "dual"
        elif has_source:
            roles[int(country_id)] = "source"
        elif has_target:
            roles[int(country_id)] = "target"
        else:
            roles[int(country_id)] = "trader"
    return roles


def _domestic_trade_reserve(country_id: int, context: TransitionContext) -> float:
    return max(
        float(context.target_totals.get(country_id, 0.0))
        - float(context.direct_local.get(country_id, 0.0))
        - float(context.trade_supply.get(country_id, 0.0)),
        0.0,
    )


def _pool_total(pool: dict[int, dict[str, float]]) -> float:
    return sum(float(bucket["current"]) + float(bucket["inventory"]) for bucket in pool.values())


def _build_country_pool(flow_map: EdgeMap, inventory_state: dict[int, dict[int, float]]) -> dict[int, dict[int, dict[str, float]]]:
    current_incoming: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for (origin, importer), value in flow_map.items():
        current_incoming[importer][origin] += float(value)

    pool: dict[int, dict[int, dict[str, float]]] = {}
    countries = set(current_incoming) | set(inventory_state)
    for country_id in countries:
        origin_ids = set(current_incoming.get(country_id, {})) | set(inventory_state.get(country_id, {}))
        pool[country_id] = {}
        for origin_id in origin_ids:
            current_value = float(current_incoming.get(country_id, {}).get(origin_id, 0.0))
            inventory_value = float(inventory_state.get(country_id, {}).get(origin_id, 0.0))
            if current_value > EPSILON or inventory_value > EPSILON:
                pool[country_id][origin_id] = {"current": current_value, "inventory": inventory_value}
    return pool


def _consume_from_pool(pool: dict[int, dict[str, float]], amount: float) -> list[dict[str, float]]:
    requested = min(float(amount), _pool_total(pool))
    if requested <= EPSILON:
        return []

    origin_totals = {origin: float(bucket["current"]) + float(bucket["inventory"]) for origin, bucket in pool.items()}
    total_available = sum(origin_totals.values())
    if total_available <= EPSILON:
        return []

    raw_uses: dict[int, float] = {}
    allocated = 0.0
    for origin, origin_total in origin_totals.items():
        use = min(origin_total, requested * origin_total / total_available)
        raw_uses[origin] = use
        allocated += use

    remainder = requested - allocated
    if remainder > EPSILON:
        for origin, origin_total in sorted(origin_totals.items(), key=lambda item: item[1], reverse=True):
            available = origin_total - raw_uses[origin]
            if available <= EPSILON:
                continue
            extra = min(available, remainder)
            raw_uses[origin] += extra
            remainder -= extra
            if remainder <= EPSILON:
                break

    allocations: list[dict[str, float]] = []
    for origin, use in raw_uses.items():
        if use <= EPSILON:
            continue
        bucket = pool[origin]
        origin_total = float(bucket["current"]) + float(bucket["inventory"])
        current_used = min(float(bucket["current"]), use * (float(bucket["current"]) / origin_total if origin_total > EPSILON else 0.0))
        inventory_used = min(float(bucket["inventory"]), use - current_used)
        leftover = use - current_used - inventory_used
        if leftover > EPSILON:
            current_slack = max(float(bucket["current"]) - current_used, 0.0)
            current_bump = min(current_slack, leftover)
            current_used += current_bump
            leftover -= current_bump
            if leftover > EPSILON:
                inventory_used += min(max(float(bucket["inventory"]) - inventory_used, 0.0), leftover)
        bucket["current"] = max(float(bucket["current"]) - current_used, 0.0)
        bucket["inventory"] = max(float(bucket["inventory"]) - inventory_used, 0.0)
        if bucket["current"] <= EPSILON and bucket["inventory"] <= EPSILON:
            pool.pop(origin, None)
        allocations.append(
            {
                "origin": int(origin),
                "current_used": float(current_used),
                "inventory_used": float(inventory_used),
                "total_used": float(current_used + inventory_used),
            }
        )
    return allocations


def reconstruct_trade_flow_v2(
    flow_map: EdgeMap,
    context: TransitionContext,
    previous_inventory: dict[int, dict[int, float]],
    params: HyperParameters,
) -> tuple[EdgeMap, dict[int, dict[int, float]], dict[str, float]]:
    final_map: EdgeMap = dict(flow_map)
    pool = _build_country_pool(flow_map, previous_inventory)
    roles = _country_roles(context)
    inventory_start_total = float(
        sum(value for origin_map in previous_inventory.values() for value in origin_map.values())
    )

    domestic_reserve_total = 0.0
    for country_id, country_pool in pool.items():
        reserve = _domestic_trade_reserve(country_id, context)
        if reserve <= EPSILON:
            continue
        consumed = _consume_from_pool(country_pool, reserve)
        domestic_reserve_total += float(sum(item["total_used"] for item in consumed))

    outgoing_edges: dict[int, dict[tuple[int, int], float]] = defaultdict(dict)
    for edge, value in flow_map.items():
        outgoing_edges[edge[0]][edge] = float(value)

    local_origin_total = 0.0
    transit_reallocated_total = 0.0
    unsupported_export_total = 0.0

    outgoing_totals = sorted(
        ((exporter, float(sum(edge_map.values()))) for exporter, edge_map in outgoing_edges.items()),
        key=lambda item: item[1],
        reverse=True,
    )

    for exporter, total_out in outgoing_totals:
        if total_out <= EPSILON:
            continue
        role = roles.get(exporter, "trader")
        local_cap = float(context.trade_supply.get(exporter, 0.0)) if role in {"source", "dual"} else 0.0
        local_total = min(total_out, local_cap)
        remaining_export = max(total_out - local_total, 0.0)
        available_transit = _pool_total(pool.get(exporter, {}))
        if role in {"source", "dual"}:
            transit_cap = remaining_export * float(params.reexport_cap)
        else:
            transit_cap = remaining_export
        transit_total = min(remaining_export, available_transit, transit_cap)
        unsupported = max(remaining_export - transit_total, 0.0)
        local_origin_total += local_total
        transit_reallocated_total += transit_total
        unsupported_export_total += unsupported

        local_share = local_total / total_out if total_out > EPSILON else 0.0
        transit_share = transit_total / total_out if total_out > EPSILON else 0.0

        for edge, edge_value in outgoing_edges[exporter].items():
            _edge_exporter, importer = edge
            local_piece = edge_value * local_share
            transit_piece = edge_value * transit_share

            if local_piece > EPSILON:
                final_map[edge] = local_piece
            else:
                final_map.pop(edge, None)

            if transit_piece <= EPSILON:
                continue
            allocations = _consume_from_pool(pool.setdefault(exporter, {}), transit_piece)
            for allocation in allocations:
                origin = int(allocation["origin"])
                current_used = float(allocation["current_used"])
                total_used = float(allocation["total_used"])
                if current_used > EPSILON:
                    upstream_edge = (origin, exporter)
                    remaining_value = float(final_map.get(upstream_edge, 0.0)) - current_used
                    if remaining_value > EPSILON:
                        final_map[upstream_edge] = remaining_value
                    else:
                        final_map.pop(upstream_edge, None)
                if total_used > EPSILON:
                    redirected_edge = (origin, importer)
                    final_map[redirected_edge] = float(final_map.get(redirected_edge, 0.0)) + total_used

    next_inventory: dict[int, dict[int, float]] = {}
    for country_id, country_pool in pool.items():
        remaining = {
            int(origin): float(bucket["current"]) + float(bucket["inventory"])
            for origin, bucket in country_pool.items()
            if float(bucket["current"]) + float(bucket["inventory"]) > EPSILON
        }
        if remaining:
            next_inventory[int(country_id)] = remaining

    inventory_end_total = float(sum(value for origin_map in next_inventory.values() for value in origin_map.values()))
    filtered_map = {edge: value for edge, value in final_map.items() if value > EPSILON}
    diagnostics = {
        "inventory_start_total": inventory_start_total,
        "inventory_end_total": inventory_end_total,
        "domestic_reserve_total": domestic_reserve_total,
        "local_origin_total": local_origin_total,
        "transit_reallocated_total": transit_reallocated_total,
        "unsupported_export_total": unsupported_export_total,
    }
    return filtered_map, next_inventory, diagnostics


def evaluate_transition(flow_map: EdgeMap, context: TransitionContext) -> dict[str, float]:
    source_ids = set(context.source_totals)
    target_ids = set(context.target_totals)
    external_incoming: dict[int, float] = {country_id: 0.0 for country_id in target_ids}
    known_exports: dict[int, float] = {country_id: 0.0 for country_id in target_ids}
    exporter_targets: dict[int, dict[int, float]] = defaultdict(dict)
    exporter_non_target: dict[int, float] = defaultdict(float)
    non_source_imports: dict[int, float] = defaultdict(float)

    for (exporter, importer), value in flow_map.items():
        if importer in target_ids:
            if exporter in source_ids:
                exporter_targets[exporter][importer] = exporter_targets[exporter].get(importer, 0.0) + value
            else:
                non_source_imports[importer] += value
        elif exporter in source_ids:
            exporter_non_target[exporter] += value

    for exporter, total in context.trade_supply.items():
        target_map = exporter_targets.get(exporter, {})
        known_total = sum(target_map.values()) + exporter_non_target.get(exporter, 0.0)
        scale = min(1.0, total / known_total) if known_total > EPSILON else 1.0
        used = 0.0
        exporter_known_exports = 0.0
        for importer, value in target_map.items():
            scaled = value * scale
            if scaled <= EPSILON:
                continue
            if importer != exporter:
                external_incoming[importer] = external_incoming.get(importer, 0.0) + scaled
                exporter_known_exports += scaled
            used += scaled
        non_target_value = exporter_non_target.get(exporter, 0.0) * scale
        if non_target_value > EPSILON:
            used += non_target_value
            exporter_known_exports += non_target_value
        self_value = max(total - used, 0.0)
        if self_value > EPSILON and exporter not in target_ids:
            exporter_known_exports += self_value
        if exporter in target_ids:
            known_exports[exporter] = known_exports.get(exporter, 0.0) + exporter_known_exports

    for importer, value in non_source_imports.items():
        external_incoming[importer] = external_incoming.get(importer, 0.0) + value

    unknown_total = 0.0
    max_country_residual = 0.0
    for country_id, target_total in context.target_totals.items():
        trade_need = max(target_total - context.direct_local.get(country_id, 0.0), 0.0)
        balance_value = context.balance_map.get(country_id, trade_need - context.trade_supply.get(country_id, 0.0))
        gap, excess = v1._resolve_balance(balance_value, external_incoming.get(country_id, 0.0), known_exports.get(country_id, 0.0))
        country_residual = gap + excess
        unknown_total += country_residual
        max_country_residual = max(max_country_residual, country_residual)

    return {
        "unknown_total": unknown_total,
        "non_source_total": float(sum(non_source_imports.values())),
        "non_target_total": float(sum(exporter_non_target.values())),
        "max_country_residual": max_country_residual,
    }


def _candidate_exporters(flow_map: EdgeMap, context: TransitionContext, roles: dict[int, str], params: HyperParameters) -> list[int]:
    outgoing = v1._country_outgoing(flow_map)
    grouped: dict[str, list[tuple[float, int]]] = {"source": [], "dual": []}
    for exporter, outflow in outgoing.items():
        role = roles.get(exporter, "trader")
        if role not in grouped:
            continue
        capacity = max(float(context.trade_supply.get(exporter, 0.0)), EPSILON)
        mismatch = abs(outflow - capacity) / capacity
        grouped[role].append((outflow * (1.0 + mismatch), exporter))
    selected: list[int] = []
    grouped["source"].sort(reverse=True)
    grouped["dual"].sort(reverse=True)
    selected.extend(exporter for _score, exporter in grouped["source"][: params.source_priority_count])
    selected.extend(exporter for _score, exporter in grouped["dual"][: params.dual_priority_count])
    return selected


def _apply_alpha_scales(flow_map: EdgeMap, multipliers: dict[int, float], context: TransitionContext, roles: dict[int, str]) -> EdgeMap:
    scaled: EdgeMap = {}
    for edge, value in flow_map.items():
        scaled_value = float(value) * float(multipliers.get(edge[0], 1.0))
        if scaled_value > EPSILON:
            scaled[edge] = scaled_value

    outgoing = v1._country_outgoing(scaled)
    for exporter, total_out in outgoing.items():
        if roles.get(exporter) not in {"source", "dual"}:
            continue
        cap = float(context.trade_supply.get(exporter, 0.0))
        if total_out <= cap + EPSILON:
            continue
        scale = cap / total_out if cap > EPSILON else 0.0
        for edge in list(scaled):
            if edge[0] != exporter:
                continue
            adjusted = scaled[edge] * scale
            if adjusted > EPSILON:
                scaled[edge] = adjusted
            else:
                scaled.pop(edge, None)
    return scaled


def _objective(metrics: dict[str, float], multipliers: dict[int, float], params: HyperParameters) -> float:
    return (
        metrics["unknown_total"]
        + params.non_source_weight * metrics["non_source_total"]
        + params.non_target_weight * metrics["non_target_total"]
        + params.max_residual_weight * metrics["max_country_residual"]
        + params.deviation_weight * sum(abs(value - 1.0) for value in multipliers.values())
    )


def optimize_transition_v2(
    flow_map: EdgeMap,
    context: TransitionContext,
    roles: dict[int, str],
    params: HyperParameters,
) -> tuple[EdgeMap, dict[int, float], dict[str, float]]:
    if not flow_map:
        return {}, {}, evaluate_transition({}, context)

    candidates = _candidate_exporters(flow_map, context, roles, params)
    multipliers = {country_id: 1.0 for country_id in candidates}
    best_map = _apply_alpha_scales(flow_map, multipliers, context, roles)
    best_metrics = evaluate_transition(best_map, context)
    best_score = _objective(best_metrics, multipliers, params)

    for _ in range(params.scale_passes):
        for exporter in candidates:
            role = roles.get(exporter, "trader")
            local_best_value = multipliers[exporter]
            local_best_map = best_map
            local_best_metrics = best_metrics
            local_best_score = best_score
            for scale in params.values_for_role(role):
                trial = dict(multipliers)
                trial[exporter] = scale
                trial_map = _apply_alpha_scales(flow_map, trial, context, roles)
                trial_metrics = evaluate_transition(trial_map, context)
                trial_score = _objective(trial_metrics, trial, params)
                if trial_score + 1e-9 < local_best_score:
                    local_best_value = scale
                    local_best_map = trial_map
                    local_best_metrics = trial_metrics
                    local_best_score = trial_score
            multipliers[exporter] = local_best_value
            best_map = local_best_map
            best_metrics = local_best_metrics
            best_score = local_best_score
    return best_map, multipliers, best_metrics


def optimize_metal_series(
    metal: str,
    params: HyperParameters,
    *,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
) -> tuple[dict[int, Any], pd.DataFrame]:
    base_inputs_by_year = {year: load_year_inputs(metal, year) for year in YEARS}
    contexts_by_year = {
        year: transition_contexts(metal, base_inputs_by_year[year], cobalt_mode=cobalt_mode) for year in YEARS
    }
    replacement_field_maps_by_year: dict[int, dict[str, EdgeMap]] = {year: {} for year in YEARS}
    transition_rows: list[dict[str, Any]] = []

    for transition_spec in v1.TRANSITIONS_BY_METAL[metal]:
        field_maps_by_year: dict[int, dict[str, EdgeMap]] = {}
        group_maps_by_year: dict[int, EdgeMap] = {}
        for year in YEARS:
            context = contexts_by_year[year][transition_spec.key]
            field_maps, group_map = v1.reconcile_group(context.folder_names, year, params.mirror_weight, params.lag_weight)
            field_maps_by_year[year] = field_maps
            group_maps_by_year[year] = group_map

        optimized_folder_maps_by_year: dict[int, dict[str, EdgeMap]] = {year: {} for year in YEARS}
        for folder_name in transition_spec.folder_names:
            inventory_state: dict[int, dict[int, float]] = {}
            for year in YEARS:
                context = contexts_by_year[year][transition_spec.key]
                folder_map = field_maps_by_year[year].get(folder_name, {})
                group_map = group_maps_by_year[year]
                hs_context = v1._folder_context(context, folder_map, group_map)
                roles = _country_roles(hs_context)
                reconstructed_map, inventory_state, diagnostics = reconstruct_trade_flow_v2(
                    folder_map,
                    hs_context,
                    inventory_state,
                    params,
                )
                optimized_map, multipliers, stage_metrics = optimize_transition_v2(
                    reconstructed_map,
                    hs_context,
                    roles,
                    params,
                )
                optimized_folder_maps_by_year[year][folder_name] = optimized_map
                transition_rows.append(
                    {
                        "metal": metal,
                        "year": year,
                        "transition": transition_spec.key,
                        "folder_name": folder_name,
                        "stage_unknown_total": stage_metrics["unknown_total"],
                        "non_source_total": stage_metrics["non_source_total"],
                        "non_target_total": stage_metrics["non_target_total"],
                        "max_country_residual": stage_metrics["max_country_residual"],
                        "inventory_start_total": diagnostics["inventory_start_total"],
                        "inventory_end_total": diagnostics["inventory_end_total"],
                        "domestic_reserve_total": diagnostics["domestic_reserve_total"],
                        "local_origin_total": diagnostics["local_origin_total"],
                        "transit_reallocated_total": diagnostics["transit_reallocated_total"],
                        "unsupported_export_total": diagnostics["unsupported_export_total"],
                        "country_roles_json": json.dumps(roles, ensure_ascii=False, sort_keys=True),
                        "multipliers_json": json.dumps(multipliers, ensure_ascii=False, sort_keys=True),
                        "params_json": json.dumps(asdict(params), ensure_ascii=False, sort_keys=True),
                    }
                )

        for year in YEARS:
            context = contexts_by_year[year][transition_spec.key]
            if len(context.input_fields) == 1:
                replacement_field_maps_by_year[year][context.input_fields[0]] = v1._merge_edge_maps(
                    *optimized_folder_maps_by_year[year].values()
                )
            else:
                for field_name, folder_name in zip(context.input_fields, context.folder_names):
                    replacement_field_maps_by_year[year][field_name] = optimized_folder_maps_by_year[year].get(folder_name, {})

    optimized_inputs_by_year = {
        year: replace_trade_fields(metal, base_inputs_by_year[year], replacement_field_maps_by_year[year]) for year in YEARS
    }
    return optimized_inputs_by_year, pd.DataFrame(transition_rows)


def run_shared_search() -> tuple[HyperParameters, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    best_params: HyperParameters | None = None
    best_score: float | None = None

    for params in HYPERPARAM_GRID:
        total_unknown = 0.0
        total_special = 0.0
        total_non_source = 0.0
        total_non_target = 0.0
        metal_unknowns: dict[str, float] = {}
        metal_specials: dict[str, float] = {}

        for metal in METALS:
            optimized_inputs_by_year, _detail = optimize_metal_series(metal, params, cobalt_mode=DEFAULT_COBALT_MODE)
            metal_unknown = 0.0
            metal_special = 0.0
            for year in YEARS:
                nodes, links = build_country_graph(
                    metal,
                    year,
                    inputs=optimized_inputs_by_year[year],
                    cobalt_mode=DEFAULT_COBALT_MODE,
                )
                _node_df, summary_df = summarize_graph(nodes, links, metal, year, "optimized")
                summary_row = summary_df.iloc[0].to_dict()
                metal_unknown += float(summary_row["unknown_total"])
                metal_special += float(summary_row["total_special"])
                total_non_source += float(summary_row["non_source_total"])
                total_non_target += float(summary_row["non_target_total"])
            metal_unknowns[metal] = metal_unknown
            metal_specials[metal] = metal_special
            total_unknown += metal_unknown
            total_special += metal_special

        score = total_unknown + 0.02 * total_special + 0.01 * (total_non_source + total_non_target)
        rows.append(
            {
                **asdict(params),
                "score": score,
                "unknown_total": total_unknown,
                "total_special": total_special,
                "non_source_total": total_non_source,
                "non_target_total": total_non_target,
                "Li_unknown_total": metal_unknowns["Li"],
                "Ni_unknown_total": metal_unknowns["Ni"],
                "Co_unknown_total": metal_unknowns["Co"],
                "Li_total_special": metal_specials["Li"],
                "Ni_total_special": metal_specials["Ni"],
                "Co_total_special": metal_specials["Co"],
            }
        )
        if best_score is None or score < best_score:
            best_score = score
            best_params = params

    if best_params is None:
        raise RuntimeError("No shared hyperparameter result was produced.")
    search_df = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
    search_df["rank"] = range(1, len(search_df) + 1)
    search_df.to_csv(COMPARISON_OUTPUT_ROOT / "hyperparameter_search.csv", index=False)
    return best_params, search_df


def export_optimized(best_params: HyperParameters) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_summary = []
    all_stage = []
    all_transition = []
    for metal in METALS:
        optimized_inputs_by_year, transition_df = optimize_metal_series(metal, best_params, cobalt_mode=DEFAULT_COBALT_MODE)
        all_transition.append(transition_df)
        for year in YEARS:
            optimized_inputs = optimized_inputs_by_year[year]
            nodes, links = build_country_graph(metal, year, inputs=optimized_inputs, cobalt_mode=DEFAULT_COBALT_MODE)
            node_df, _link_df, summary_df = _write_case_exports(
                OPTIMIZED_OUTPUT_ROOT,
                metal,
                year,
                "optimized",
                optimized_inputs,
                nodes,
                links,
                {"best_params": asdict(best_params), "metal": metal, "optimization_version": "v2"},
            )
            all_summary.append(summary_df)
            all_stage.append(stage_summary(node_df))
    optimized_summary = pd.concat(all_summary, ignore_index=True)
    optimized_stage = pd.concat(all_stage, ignore_index=True)
    transition_detail = pd.concat(all_transition, ignore_index=True)
    optimized_summary.to_csv(COMPARISON_OUTPUT_ROOT / "optimized_summary.csv", index=False)
    optimized_stage.to_csv(COMPARISON_OUTPUT_ROOT / "optimized_stage_summary.csv", index=False)
    transition_detail.to_csv(COMPARISON_OUTPUT_ROOT / "optimized_transition_detail.csv", index=False)
    return optimized_summary, optimized_stage, transition_detail


def build_comparison_workbook(
    baseline_summary: pd.DataFrame,
    optimized_summary: pd.DataFrame,
    baseline_stage: pd.DataFrame,
    optimized_stage: pd.DataFrame,
    search_df: pd.DataFrame,
    transition_detail: pd.DataFrame,
    best_params: HyperParameters,
) -> pd.DataFrame:
    comparison = baseline_summary.merge(optimized_summary, on=["metal", "year"], suffixes=("_baseline", "_optimized"))
    comparison["unknown_reduction"] = comparison["unknown_total_baseline"] - comparison["unknown_total_optimized"]
    comparison["unknown_reduction_pct"] = comparison["unknown_reduction"] / comparison["unknown_total_baseline"].replace(0, pd.NA)
    comparison["special_reduction"] = comparison["total_special_baseline"] - comparison["total_special_optimized"]
    comparison.to_csv(COMPARISON_OUTPUT_ROOT / "comparison_summary.csv", index=False)

    best_params_df = pd.DataFrame([{"scope": "shared", **asdict(best_params)}])
    workbook_path = SPREADSHEET_OUTPUT_ROOT / "trade_flow_comparison.xlsx"
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        comparison.to_excel(writer, sheet_name="summary", index=False)
        baseline_summary.to_excel(writer, sheet_name="baseline_metrics", index=False)
        optimized_summary.to_excel(writer, sheet_name="optimized_metrics", index=False)
        baseline_stage.to_excel(writer, sheet_name="baseline_stage", index=False)
        optimized_stage.to_excel(writer, sheet_name="optimized_stage", index=False)
        search_df.to_excel(writer, sheet_name="hyperparams", index=False)
        transition_detail.to_excel(writer, sheet_name="transition_detail", index=False)
        best_params_df.to_excel(writer, sheet_name="best_params", index=False)
    return comparison


def _build_feasibility_summary(comparison: pd.DataFrame, best_params: HyperParameters) -> dict[str, Any]:
    by_metal: dict[str, Any] = {}
    for metal in METALS:
        metal_slice = comparison.loc[comparison["metal"] == metal]
        by_metal[metal] = {
            "best_params": asdict(best_params),
            "total_unknown_reduction": float(metal_slice["unknown_reduction"].sum()),
            "cases_improved": int((metal_slice["unknown_reduction"] > 0).sum()),
            "case_count": int(len(metal_slice)),
        }
    return {
        "optimization_version": "v2",
        "shared_best_params": asdict(best_params),
        "best_params_by_metal": by_metal,
        "mean_unknown_reduction": float(comparison["unknown_reduction"].mean()),
        "median_unknown_reduction": float(comparison["unknown_reduction"].median()),
        "cases_improved": int((comparison["unknown_reduction"] > 0).sum()),
        "case_count": int(len(comparison)),
    }


def _snapshot_v2_outputs() -> None:
    V2_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    output_snapshot = V2_SNAPSHOT_ROOT / "output"
    if output_snapshot.exists():
        shutil.rmtree(output_snapshot)
    shutil.copytree(OUTPUT_ROOT, output_snapshot)
    shutil.copy2(Path(__file__), V2_SNAPSHOT_ROOT / "pipeline_v2.py")


def _build_version_comparison() -> pd.DataFrame | None:
    v1_comparison_path = V1_SNAPSHOT_ROOT / "output" / "comparison" / "comparison_summary.csv"
    if not v1_comparison_path.exists() or not (COMPARISON_OUTPUT_ROOT / "comparison_summary.csv").exists():
        return None
    v1_comparison = pd.read_csv(v1_comparison_path)
    v2_comparison = pd.read_csv(COMPARISON_OUTPUT_ROOT / "comparison_summary.csv")
    merged = v1_comparison[
        ["metal", "year", "unknown_reduction", "unknown_reduction_pct", "special_reduction"]
    ].merge(
        v2_comparison[["metal", "year", "unknown_reduction", "unknown_reduction_pct", "special_reduction"]],
        on=["metal", "year"],
        suffixes=("_v1", "_v2"),
    )
    merged["unknown_reduction_delta_v2_minus_v1"] = (
        merged["unknown_reduction_v2"] - merged["unknown_reduction_v1"]
    )
    merged["special_reduction_delta_v2_minus_v1"] = (
        merged["special_reduction_v2"] - merged["special_reduction_v1"]
    )
    merged.to_csv(VERSION_OUTPUT_ROOT / "version_comparison_v1_v2.csv", index=False)
    return merged


def main() -> None:
    _ensure_output_dirs()
    baseline_summary, baseline_stage = export_baseline()
    best_params, search_df = run_shared_search()
    optimized_summary, optimized_stage, transition_detail = export_optimized(best_params)
    comparison = build_comparison_workbook(
        baseline_summary,
        optimized_summary,
        baseline_stage,
        optimized_stage,
        search_df,
        transition_detail,
        best_params,
    )
    result = _build_feasibility_summary(comparison, best_params)
    with (COMPARISON_OUTPUT_ROOT / "feasibility_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    _snapshot_v2_outputs()
    version_comparison = _build_version_comparison()
    if version_comparison is not None:
        result["version_comparison_rows"] = int(len(version_comparison))
        with (VERSION_OUTPUT_ROOT / "version_comparison_summary.json").open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mean_unknown_reduction_delta_v2_minus_v1": float(
                        version_comparison["unknown_reduction_delta_v2_minus_v1"].mean()
                    ),
                    "median_unknown_reduction_delta_v2_minus_v1": float(
                        version_comparison["unknown_reduction_delta_v2_minus_v1"].median()
                    ),
                    "cases_where_v2_improves_over_v1": int(
                        (version_comparison["unknown_reduction_delta_v2_minus_v1"] > 0).sum()
                    ),
                    "case_count": int(len(version_comparison)),
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
