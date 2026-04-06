from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from trade_flow_opt import pipeline_v1 as v1
from trade_flow_opt import pipeline_v3 as v3
from trade_flow_opt.v4_config import HS_ROLE_CONFIG, HSRoleSpec


v3.HS_ROLE_CONFIG = HS_ROLE_CONFIG

PROJECT_ROOT = v1.PROJECT_ROOT
OUTPUT_ROOT = v1.OUTPUT_ROOT
BASELINE_OUTPUT_ROOT = v1.BASELINE_OUTPUT_ROOT
OPTIMIZED_OUTPUT_ROOT = v1.OPTIMIZED_OUTPUT_ROOT
COMPARISON_OUTPUT_ROOT = v1.COMPARISON_OUTPUT_ROOT
SPREADSHEET_OUTPUT_ROOT = v1.SPREADSHEET_OUTPUT_ROOT
INTERMEDIATE_OUTPUT_ROOT = OUTPUT_ROOT / "intermediate"
VERSION_OUTPUT_ROOT = PROJECT_ROOT / "output_versions"
V3_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v3"
V4_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v4"

METALS = v1.METALS
YEARS = v1.YEARS
DEFAULT_COBALT_MODE = v1.DEFAULT_COBALT_MODE
EPSILON = v1.EPSILON

TransitionContext = v1.TransitionContext
TransitionSpec = v1.TransitionSpec
EdgeMap = v1.EdgeMap
CoefficientKey = v3.CoefficientKey
FolderYearData = v3.FolderYearData
TransitionSeries = v3.TransitionSeries

load_year_inputs = v1.load_year_inputs
build_country_graph = v1.build_country_graph
build_country_payload = v1.build_country_payload
serialize_inputs = v1.serialize_inputs
replace_trade_fields = v1.replace_trade_fields
summarize_graph = v1.summarize_graph
stage_summary = v1.stage_summary
transition_contexts = v1.transition_contexts
export_baseline = v1.export_baseline
_write_case_exports = v3._write_case_exports
_merge_maps = v1._merge_edge_maps
_sum_maps = v1._sum_maps
_map_from_fields = v3._map_from_fields
_classify_edge = v3._classify_edge
_coefficient_key = v3._coefficient_key
_coefficient_grid = v3._coefficient_grid
_coefficient_bounds = v3._coefficient_bounds
_coefficient_delta = v3._coefficient_delta
_regularization_cost = v3._regularization_cost
_smooth_penalty = v3._smooth_penalty
_source_cap_map = v3._source_cap_map
_build_folder_year_data = v3._build_folder_year_data
_build_transition_series = v3._build_transition_series
_exposure_share = v3._exposure_share
_folder_coefficient_summary = v3._folder_coefficient_summary


@dataclass(frozen=True)
class HyperParameters:
    unknown_source_weight: float
    unknown_destination_weight: float
    non_source_weight: float
    non_target_weight: float
    max_residual_weight: float
    pp_penalty: float
    pn_up_penalty: float
    pn_down_penalty: float
    np_up_penalty: float
    np_down_penalty: float
    pp_smooth_penalty: float
    pn_smooth_penalty: float
    np_smooth_penalty: float
    shared_pp_priority: float
    shared_pn_priority: float
    coefficient_step: float
    coordinate_passes: int


HYPERPARAM_GRID = (
    HyperParameters(1.05, 1.00, 0.04, 0.04, 0.06, 0.05, 0.22, 0.03, 0.24, 0.03, 0.05, 0.06, 0.06, 1.65, 0.70, 0.05, 2),
    HyperParameters(1.10, 1.00, 0.04, 0.04, 0.08, 0.05, 0.24, 0.03, 0.28, 0.03, 0.06, 0.07, 0.07, 1.85, 0.65, 0.05, 2),
    HyperParameters(1.15, 1.05, 0.05, 0.05, 0.10, 0.06, 0.26, 0.04, 0.30, 0.04, 0.07, 0.08, 0.08, 2.00, 0.60, 0.05, 3),
)


def _ensure_output_dirs() -> None:
    for path in (
        BASELINE_OUTPUT_ROOT,
        OPTIMIZED_OUTPUT_ROOT,
        COMPARISON_OUTPUT_ROOT,
        SPREADSHEET_OUTPUT_ROOT,
        INTERMEDIATE_OUTPUT_ROOT,
        VERSION_OUTPUT_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _exporter_class_totals(edge_map: EdgeMap, edge_classes: dict[tuple[int, int], str], exporter: int) -> tuple[float, float]:
    pp_total = 0.0
    pn_total = 0.0
    for edge, value in edge_map.items():
        if edge[0] != exporter:
            continue
        edge_class = edge_classes.get(edge, "NN")
        if edge_class == "PP":
            pp_total += float(value)
        elif edge_class == "PN":
            pn_total += float(value)
    return pp_total, pn_total


def _allocate_weighted_folder_caps(rows: list[dict[str, float]], total_cap: float) -> dict[str, float]:
    allocations = {str(row["folder_name"]): 0.0 for row in rows}
    remaining_cap = max(float(total_cap), 0.0)
    active = [
        {
            "folder_name": str(row["folder_name"]),
            "remaining": float(row["desired_total"]),
            "weight": max(float(row["weight"]), EPSILON),
        }
        for row in rows
        if float(row["desired_total"]) > EPSILON
    ]
    while active and remaining_cap > EPSILON:
        total_weight = sum(row["weight"] for row in active)
        if total_weight <= EPSILON:
            break
        allocated_now = 0.0
        next_active = []
        for row in active:
            provisional = remaining_cap * row["weight"] / total_weight
            grant = min(row["remaining"], provisional)
            allocations[row["folder_name"]] += grant
            allocated_now += grant
            row["remaining"] -= grant
            if row["remaining"] > EPSILON:
                next_active.append(row)
        if allocated_now <= EPSILON:
            break
        remaining_cap = max(remaining_cap - allocated_now, 0.0)
        active = next_active
    return allocations


def _apply_prioritized_export_cap(
    edge_map: EdgeMap,
    folder_data: FolderYearData,
    cap_by_exporter: dict[int, float],
    fallback_cap: dict[int, float],
    pp_priority: float,
    pn_priority: float,
) -> EdgeMap:
    if not cap_by_exporter and not fallback_cap:
        return {edge: value for edge, value in edge_map.items() if value > EPSILON}
    adjusted = dict(edge_map)
    for exporter in folder_data.source_producers:
        cap = float(cap_by_exporter.get(exporter, fallback_cap.get(exporter, 0.0)))
        exporter_edges = [edge for edge in adjusted if edge[0] == exporter]
        if not exporter_edges:
            continue
        total_out = float(sum(adjusted[edge] for edge in exporter_edges))
        if total_out <= cap + EPSILON:
            continue
        pp_total, pn_total = _exporter_class_totals(adjusted, folder_data.edge_classes, exporter)
        allocations = _allocate_weighted_folder_caps(
            [
                {"folder_name": "PP", "desired_total": pp_total, "weight": pp_total * max(pp_priority, EPSILON)},
                {"folder_name": "PN", "desired_total": pn_total, "weight": pn_total * max(pn_priority, EPSILON)},
            ],
            cap,
        )
        pp_cap = allocations.get("PP", 0.0)
        pn_cap = allocations.get("PN", 0.0)
        pp_scale = min(1.0, pp_cap / pp_total) if pp_total > EPSILON else 1.0
        pn_scale = min(1.0, pn_cap / pn_total) if pn_total > EPSILON else 1.0
        for edge in list(exporter_edges):
            edge_class = folder_data.edge_classes.get(edge, "NN")
            if edge_class == "PP":
                scaled = adjusted[edge] * pp_scale
            elif edge_class == "PN":
                scaled = adjusted[edge] * pn_scale
            else:
                scaled = adjusted[edge]
            if scaled > EPSILON:
                adjusted[edge] = scaled
            else:
                adjusted.pop(edge, None)
    return {edge: value for edge, value in adjusted.items() if value > EPSILON}

def _build_year_folder_maps(
    series: TransitionSeries,
    year: int,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    params: HyperParameters,
    override: tuple[CoefficientKey, float] | None = None,
) -> dict[str, EdgeMap]:
    folder_maps: dict[str, EdgeMap] = {}
    year_folder_data = series.folder_data_by_year[year]
    context = series.context_by_year[year]

    for folder_name, folder_data in year_folder_data.items():
        if not folder_data.spec.optimize:
            continue
        built_map: EdgeMap = {}
        for edge, raw_value in folder_data.raw_map.items():
            if raw_value <= EPSILON:
                continue
            edge_class = folder_data.edge_classes[edge]
            coefficient_key = _coefficient_key(folder_name, edge_class, edge[0], edge[1])
            coefficient = 1.0
            if coefficient_key is not None:
                if override is not None and override[0] == coefficient_key:
                    coefficient = float(override[1])
                else:
                    coefficient = float(coefficient_paths.get(coefficient_key, {}).get(year, 1.0))
            adjusted = float(raw_value) * coefficient
            if adjusted > EPSILON:
                built_map[edge] = adjusted
        folder_maps[folder_name] = built_map

    for folder_name, folder_data in year_folder_data.items():
        if not folder_data.spec.optimize or not folder_data.spec.exact_source_cap_fields:
            continue
        cap_map = _source_cap_map(folder_data, context)
        fallback_cap = {int(country): float(value) for country, value in context.trade_supply.items()}
        folder_maps[folder_name] = _apply_prioritized_export_cap(
            folder_maps.get(folder_name, {}),
            folder_data,
            {},
            {**fallback_cap, **cap_map},
            params.shared_pp_priority,
            params.shared_pn_priority,
        )

    shared_folders = [
        folder_name
        for folder_name, folder_data in year_folder_data.items()
        if folder_data.spec.optimize and folder_data.spec.use_transition_supply_cap
    ]
    if shared_folders:
        caps_by_folder: dict[str, dict[int, float]] = {folder_name: {} for folder_name in shared_folders}
        shared_exporters: set[int] = set()
        for folder_name in shared_folders:
            shared_exporters.update(year_folder_data[folder_name].source_producers)
        for exporter in shared_exporters:
            rows: list[dict[str, float]] = []
            for folder_name in shared_folders:
                folder_map = folder_maps.get(folder_name, {})
                folder_data = year_folder_data[folder_name]
                pp_total, pn_total = _exporter_class_totals(folder_map, folder_data.edge_classes, exporter)
                desired_total = pp_total + pn_total
                weight = params.shared_pp_priority * pp_total + params.shared_pn_priority * pn_total
                rows.append(
                    {
                        "folder_name": folder_name,
                        "desired_total": desired_total,
                        "weight": weight if weight > EPSILON else desired_total,
                    }
                )
            allocations = _allocate_weighted_folder_caps(rows, float(context.trade_supply.get(exporter, 0.0)))
            for folder_name, value in allocations.items():
                caps_by_folder[folder_name][exporter] = value
        for folder_name in shared_folders:
            folder_maps[folder_name] = _apply_prioritized_export_cap(
                folder_maps.get(folder_name, {}),
                year_folder_data[folder_name],
                caps_by_folder.get(folder_name, {}),
                {},
                params.shared_pp_priority,
                params.shared_pn_priority,
            )

    return {
        folder_name: {edge: value for edge, value in folder_map.items() if value > EPSILON}
        for folder_name, folder_map in folder_maps.items()
    }


def evaluate_transition_v4(flow_map: EdgeMap, context: TransitionContext) -> dict[str, float]:
    source_ids = set(context.source_totals)
    target_ids = set(context.target_totals)
    external_incoming: dict[int, float] = {country_id: 0.0 for country_id in target_ids}
    known_exports: dict[int, float] = {country_id: 0.0 for country_id in target_ids}
    exporter_targets: dict[int, dict[int, float]] = {}
    exporter_non_target: dict[int, float] = {}
    non_source_imports: dict[int, float] = {}

    for (exporter, importer), value in flow_map.items():
        if importer in target_ids:
            if exporter in source_ids:
                exporter_targets.setdefault(exporter, {})
                exporter_targets[exporter][importer] = exporter_targets[exporter].get(importer, 0.0) + value
            else:
                non_source_imports[importer] = non_source_imports.get(importer, 0.0) + value
        elif exporter in source_ids:
            exporter_non_target[exporter] = exporter_non_target.get(exporter, 0.0) + value

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

    unknown_source_total = 0.0
    unknown_destination_total = 0.0
    max_country_residual = 0.0
    for country_id, target_total in context.target_totals.items():
        trade_need = max(target_total - context.direct_local.get(country_id, 0.0), 0.0)
        balance_value = context.balance_map.get(country_id, trade_need - context.trade_supply.get(country_id, 0.0))
        gap, excess = v1._resolve_balance(balance_value, external_incoming.get(country_id, 0.0), known_exports.get(country_id, 0.0))
        unknown_source_total += gap
        unknown_destination_total += excess
        max_country_residual = max(max_country_residual, gap + excess)

    return {
        "unknown_source_total": unknown_source_total,
        "unknown_destination_total": unknown_destination_total,
        "unknown_total": unknown_source_total + unknown_destination_total,
        "non_source_total": float(sum(non_source_imports.values())),
        "non_target_total": float(sum(exporter_non_target.values())),
        "max_country_residual": max_country_residual,
    }


def _evaluate_transition_year(
    series: TransitionSeries,
    year: int,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    params: HyperParameters,
    override: tuple[CoefficientKey, float] | None = None,
) -> tuple[dict[str, float], dict[str, EdgeMap]]:
    folder_maps = _build_year_folder_maps(series, year, coefficient_paths, params, override=override)
    combined_map = _merge_maps(*folder_maps.values()) if folder_maps else {}
    metrics = evaluate_transition_v4(combined_map, series.context_by_year[year])
    return metrics, folder_maps


def _base_residual_cost(metrics: dict[str, float], params: HyperParameters) -> float:
    return (
        params.unknown_source_weight * float(metrics["unknown_source_total"])
        + params.unknown_destination_weight * float(metrics["unknown_destination_total"])
        + params.non_source_weight * float(metrics["non_source_total"])
        + params.non_target_weight * float(metrics["non_target_total"])
        + params.max_residual_weight * float(metrics["max_country_residual"])
    )


def _local_year_cost(
    series: TransitionSeries,
    year: int,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    coefficient_key: CoefficientKey,
    candidate_value: float,
    params: HyperParameters,
) -> float:
    metrics, _folder_maps = _evaluate_transition_year(series, year, coefficient_paths, params, override=(coefficient_key, candidate_value))
    residual_cost = _base_residual_cost(metrics, params)
    exposure_share = _exposure_share(series, coefficient_key, year)
    regularization_cost = _regularization_cost(coefficient_key.coefficient_class, candidate_value, exposure_share, params)
    return residual_cost + regularization_cost


def _transition_cost(
    series: TransitionSeries,
    coefficient_key: CoefficientKey,
    previous_year: int,
    current_year: int,
    previous_value: float,
    current_value: float,
    params: HyperParameters,
) -> float | None:
    prev_share = _exposure_share(series, coefficient_key, previous_year)
    current_share = _exposure_share(series, coefficient_key, current_year)
    if prev_share <= EPSILON or current_share <= EPSILON:
        return 0.0
    delta = abs(float(current_value) - float(previous_value))
    max_delta = _coefficient_delta(series.coefficient_meta[coefficient_key]["spec"], coefficient_key.coefficient_class)
    if delta > max_delta + 1e-9:
        return None
    return _smooth_penalty(coefficient_key.coefficient_class, delta, (prev_share + current_share) / 2.0, params)


def _optimize_coefficient_path(
    series: TransitionSeries,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    coefficient_key: CoefficientKey,
    params: HyperParameters,
) -> dict[int, float]:
    meta = series.coefficient_meta[coefficient_key]
    values = _coefficient_grid(meta["spec"], coefficient_key.coefficient_class, params.coefficient_step)
    if values == [1.0]:
        return {year: 1.0 for year in YEARS}

    local_costs: dict[int, dict[float, float]] = {}
    for year in YEARS:
        local_costs[year] = {value: _local_year_cost(series, year, coefficient_paths, coefficient_key, value, params) for value in values}

    states: dict[float, float] = {value: local_costs[YEARS[0]][value] for value in values}
    backtrack: dict[tuple[int, float], float | None] = {(0, value): None for value in values}

    for index, year in enumerate(YEARS[1:], start=1):
        previous_year = YEARS[index - 1]
        next_states: dict[float, float] = {}
        for value in values:
            best_cost: float | None = None
            best_previous: float | None = None
            for previous_value, previous_cost in states.items():
                transition_cost = _transition_cost(series, coefficient_key, previous_year, year, previous_value, value, params)
                if transition_cost is None:
                    continue
                total_cost = previous_cost + transition_cost + local_costs[year][value]
                if best_cost is None or total_cost < best_cost - 1e-9:
                    best_cost = total_cost
                    best_previous = previous_value
            if best_cost is not None:
                next_states[value] = best_cost
                backtrack[(index, value)] = best_previous
        if not next_states:
            current_path = coefficient_paths.get(coefficient_key, {})
            return {year_value: float(current_path.get(year_value, 1.0)) for year_value in YEARS}
        states = next_states

    best_end_value = min(states, key=states.get)
    path: dict[int, float] = {}
    current_value: float | None = best_end_value
    for index in reversed(range(len(YEARS))):
        year = YEARS[index]
        if current_value is None:
            current_value = 1.0
        path[year] = float(current_value)
        current_value = backtrack.get((index, current_value))
    return path


def _build_coefficient_paths(series: TransitionSeries) -> dict[CoefficientKey, dict[int, float]]:
    return {coefficient_key: {year: 1.0 for year in YEARS} for coefficient_key in series.coefficient_order}

def optimize_transition_series_v4(series: TransitionSeries, params: HyperParameters) -> tuple[dict[int, dict[str, EdgeMap]], pd.DataFrame, pd.DataFrame]:
    if not any(folder_data.spec.optimize for folder_map in series.folder_data_by_year.values() for folder_data in folder_map.values()):
        rows = [
            {
                "metal": series.metal,
                "year": year,
                "transition": series.transition_spec.key,
                "folder_name": folder_name,
                "optimize_enabled": False,
                "skipped_reason": HS_ROLE_CONFIG[folder_name].note or "Synthetic / non-Comtrade bucket",
                "unknown_source_total": 0.0,
                "unknown_destination_total": 0.0,
                "stage_unknown_total": 0.0,
                "non_source_total": 0.0,
                "non_target_total": 0.0,
                "max_country_residual": 0.0,
                "folder_raw_total": 0.0,
                "folder_optimized_total": 0.0,
                "pp_edge_count": 0,
                "pn_edge_count": 0,
                "np_edge_count": 0,
                "nn_edge_count": 0,
                "source_producer_count": 0,
                "target_producer_count": 0,
                "coefficient_count": 0,
                "bound_hit_count": 0,
                "source_producers_json": "[]",
                "target_producers_json": "[]",
                "coefficient_summary_json": "{}",
                "params_json": json.dumps(asdict(params), ensure_ascii=False, sort_keys=True),
            }
            for year in YEARS
            for folder_name in series.transition_spec.folder_names
        ]
        return {year: {} for year in YEARS}, pd.DataFrame(rows), pd.DataFrame()

    coefficient_paths = _build_coefficient_paths(series)
    for _ in range(params.coordinate_passes):
        for coefficient_key in series.coefficient_order:
            coefficient_paths[coefficient_key] = _optimize_coefficient_path(series, coefficient_paths, coefficient_key, params)

    folder_maps_by_year: dict[int, dict[str, EdgeMap]] = {}
    transition_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []

    for year in YEARS:
        metrics, folder_maps = _evaluate_transition_year(series, year, coefficient_paths, params)
        folder_maps_by_year[year] = folder_maps
        year_folder_data = series.folder_data_by_year[year]
        for folder_name in series.transition_spec.folder_names:
            folder_data = year_folder_data[folder_name]
            coefficient_summary, bound_hit_count = _folder_coefficient_summary(series, coefficient_paths, folder_name, year)
            transition_rows.append(
                {
                    "metal": series.metal,
                    "year": year,
                    "transition": series.transition_spec.key,
                    "folder_name": folder_name,
                    "optimize_enabled": bool(folder_data.spec.optimize),
                    "skipped_reason": "" if folder_data.spec.optimize else (folder_data.spec.note or "Synthetic / non-Comtrade bucket"),
                    "unknown_source_total": float(metrics["unknown_source_total"]),
                    "unknown_destination_total": float(metrics["unknown_destination_total"]),
                    "stage_unknown_total": float(metrics["unknown_total"]),
                    "non_source_total": float(metrics["non_source_total"]),
                    "non_target_total": float(metrics["non_target_total"]),
                    "max_country_residual": float(metrics["max_country_residual"]),
                    "folder_raw_total": float(folder_data.raw_total),
                    "folder_optimized_total": float(sum(folder_maps.get(folder_name, {}).values())),
                    "pp_edge_count": int(folder_data.edge_count_by_class["PP"]),
                    "pn_edge_count": int(folder_data.edge_count_by_class["PN"]),
                    "np_edge_count": int(folder_data.edge_count_by_class["NP"]),
                    "nn_edge_count": int(folder_data.edge_count_by_class["NN"]),
                    "source_producer_count": int(len(folder_data.source_producers)),
                    "target_producer_count": int(len(folder_data.target_producers)),
                    "coefficient_count": int(sum(1 for coefficient_key, meta in series.coefficient_meta.items() if meta["folder_name"] == folder_name and float(series.exposure_by_key_year.get(coefficient_key, {}).get(year, 0.0)) > EPSILON)),
                    "bound_hit_count": int(bound_hit_count),
                    "source_producers_json": json.dumps(sorted(folder_data.source_producers), ensure_ascii=False),
                    "target_producers_json": json.dumps(sorted(folder_data.target_producers), ensure_ascii=False),
                    "coefficient_summary_json": json.dumps(coefficient_summary, ensure_ascii=False, sort_keys=True),
                    "params_json": json.dumps(asdict(params), ensure_ascii=False, sort_keys=True),
                }
            )

    for coefficient_key, meta in series.coefficient_meta.items():
        lower, upper = _coefficient_bounds(meta["spec"], coefficient_key.coefficient_class)
        for year in YEARS:
            exposure = float(series.exposure_by_key_year.get(coefficient_key, {}).get(year, 0.0))
            value = float(coefficient_paths[coefficient_key][year])
            coefficient_rows.append(
                {
                    "metal": series.metal,
                    "year": year,
                    "transition": series.transition_spec.key,
                    "folder_name": meta["folder_name"],
                    "coefficient_class": coefficient_key.coefficient_class,
                    "coefficient_id": coefficient_key.label(),
                    "exporter": coefficient_key.exporter,
                    "importer": coefficient_key.importer,
                    "coef_value": value,
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "hit_lower": int(abs(value - lower) <= 1e-9),
                    "hit_upper": int(abs(value - upper) <= 1e-9),
                    "exposure": exposure,
                    "exposure_share": _exposure_share(series, coefficient_key, year),
                }
            )

    return folder_maps_by_year, pd.DataFrame(transition_rows), pd.DataFrame(coefficient_rows)


def optimize_metal_series(metal: str, params: HyperParameters, *, cobalt_mode: str = DEFAULT_COBALT_MODE) -> tuple[dict[int, Any], pd.DataFrame, pd.DataFrame]:
    base_inputs_by_year = {year: load_year_inputs(metal, year) for year in YEARS}
    contexts_by_year = {year: transition_contexts(metal, base_inputs_by_year[year], cobalt_mode=cobalt_mode) for year in YEARS}
    replacement_field_maps_by_year: dict[int, dict[str, EdgeMap]] = {year: {} for year in YEARS}
    transition_frames: list[pd.DataFrame] = []
    coefficient_frames: list[pd.DataFrame] = []

    for transition_spec in v1.TRANSITIONS_BY_METAL[metal]:
        series = _build_transition_series(metal, transition_spec, base_inputs_by_year, contexts_by_year)
        folder_maps_by_year, transition_df, coefficient_df = optimize_transition_series_v4(series, params)
        if not transition_df.empty:
            transition_frames.append(transition_df)
        if not coefficient_df.empty:
            coefficient_frames.append(coefficient_df)

        optimize_folders = {folder_name for folder_name in transition_spec.folder_names if HS_ROLE_CONFIG[folder_name].optimize}
        if not optimize_folders:
            continue

        for year in YEARS:
            context = contexts_by_year[year][transition_spec.key]
            year_folder_maps = folder_maps_by_year.get(year, {})
            if len(context.input_fields) == 1:
                merged = _merge_maps(*(year_folder_maps.get(folder_name, {}) for folder_name in optimize_folders))
                replacement_field_maps_by_year[year][context.input_fields[0]] = merged
            else:
                for field_name, folder_name in zip(context.input_fields, context.folder_names):
                    if folder_name not in optimize_folders:
                        continue
                    replacement_field_maps_by_year[year][field_name] = year_folder_maps.get(folder_name, {})

    optimized_inputs_by_year = {year: replace_trade_fields(metal, base_inputs_by_year[year], replacement_field_maps_by_year[year]) for year in YEARS}
    transition_detail = pd.concat(transition_frames, ignore_index=True) if transition_frames else pd.DataFrame()
    coefficient_detail = pd.concat(coefficient_frames, ignore_index=True) if coefficient_frames else pd.DataFrame()
    return optimized_inputs_by_year, transition_detail, coefficient_detail


def run_shared_search(*, cobalt_mode: str = DEFAULT_COBALT_MODE, write_search_csv: bool = True) -> tuple[HyperParameters, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    best_params: HyperParameters | None = None
    best_score: float | None = None

    for params in HYPERPARAM_GRID:
        total_unknown = 0.0
        total_unknown_source = 0.0
        total_unknown_destination = 0.0
        total_special = 0.0
        total_non_source = 0.0
        total_non_target = 0.0
        total_bound_hits = 0
        total_coefficients = 0
        metal_unknowns: dict[str, float] = {}

        for metal in METALS:
            optimized_inputs_by_year, transition_df, coefficient_df = optimize_metal_series(metal, params, cobalt_mode=cobalt_mode)
            metal_unknown = 0.0
            if not transition_df.empty:
                total_unknown_source += float(transition_df["unknown_source_total"].sum())
                total_unknown_destination += float(transition_df["unknown_destination_total"].sum())
            for year in YEARS:
                nodes, links = build_country_graph(metal, year, inputs=optimized_inputs_by_year[year], cobalt_mode=cobalt_mode)
                _node_df, summary_df = summarize_graph(nodes, links, metal, year, "optimized")
                summary_row = summary_df.iloc[0].to_dict()
                metal_unknown += float(summary_row["unknown_total"])
                total_special += float(summary_row["total_special"])
                total_non_source += float(summary_row["non_source_total"])
                total_non_target += float(summary_row["non_target_total"])
            if not coefficient_df.empty:
                total_bound_hits += int(coefficient_df["hit_lower"].sum() + coefficient_df["hit_upper"].sum())
                total_coefficients += int(len(coefficient_df))
            metal_unknowns[metal] = metal_unknown
            total_unknown += metal_unknown

        bound_hit_rate = float(total_bound_hits / total_coefficients) if total_coefficients else 0.0
        score = total_unknown + 0.02 * total_special + 0.01 * (total_non_source + total_non_target) + 500.0 * bound_hit_rate
        rows.append({**asdict(params), "score": score, "unknown_total": total_unknown, "unknown_source_total": total_unknown_source, "unknown_destination_total": total_unknown_destination, "total_special": total_special, "non_source_total": total_non_source, "non_target_total": total_non_target, "bound_hit_rate": bound_hit_rate, "Li_unknown_total": metal_unknowns["Li"], "Ni_unknown_total": metal_unknowns["Ni"], "Co_unknown_total": metal_unknowns["Co"]})
        if best_score is None or score < best_score:
            best_score = score
            best_params = params

    if best_params is None:
        raise RuntimeError("No V4 hyperparameter result was produced.")
    search_df = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
    search_df["rank"] = range(1, len(search_df) + 1)
    if write_search_csv:
        search_df.to_csv(COMPARISON_OUTPUT_ROOT / "hyperparameter_search.csv", index=False)
    return best_params, search_df


def run_cobalt_search(*, cobalt_mode: str = DEFAULT_COBALT_MODE, write_search_csv: bool = False) -> tuple[HyperParameters, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    best_params: HyperParameters | None = None
    best_score: float | None = None

    for params in HYPERPARAM_GRID:
        optimized_inputs_by_year, transition_df, coefficient_df = optimize_metal_series("Co", params, cobalt_mode=cobalt_mode)
        total_unknown = 0.0
        total_unknown_source = float(transition_df["unknown_source_total"].sum()) if not transition_df.empty else 0.0
        total_unknown_destination = float(transition_df["unknown_destination_total"].sum()) if not transition_df.empty else 0.0
        total_special = 0.0
        total_non_source = 0.0
        total_non_target = 0.0
        for year in YEARS:
            nodes, links = build_country_graph("Co", year, inputs=optimized_inputs_by_year[year], cobalt_mode=cobalt_mode)
            _node_df, summary_df = summarize_graph(nodes, links, "Co", year, "optimized")
            summary_row = summary_df.iloc[0].to_dict()
            total_unknown += float(summary_row["unknown_total"])
            total_special += float(summary_row["total_special"])
            total_non_source += float(summary_row["non_source_total"])
            total_non_target += float(summary_row["non_target_total"])
        total_bound_hits = int(coefficient_df["hit_lower"].sum() + coefficient_df["hit_upper"].sum()) if not coefficient_df.empty else 0
        total_coefficients = int(len(coefficient_df))
        bound_hit_rate = float(total_bound_hits / total_coefficients) if total_coefficients else 0.0
        score = total_unknown + 0.02 * total_special + 0.01 * (total_non_source + total_non_target) + 500.0 * bound_hit_rate
        rows.append(
            {
                **asdict(params),
                "score": score,
                "unknown_total": total_unknown,
                "unknown_source_total": total_unknown_source,
                "unknown_destination_total": total_unknown_destination,
                "total_special": total_special,
                "non_source_total": total_non_source,
                "non_target_total": total_non_target,
                "bound_hit_rate": bound_hit_rate,
                "Co_unknown_total": total_unknown,
            }
        )
        if best_score is None or score < best_score:
            best_score = score
            best_params = params

    if best_params is None:
        raise RuntimeError("No V4 cobalt hyperparameter result was produced.")
    search_df = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
    search_df["rank"] = range(1, len(search_df) + 1)
    if write_search_csv:
        search_df.to_csv(COMPARISON_OUTPUT_ROOT / f"hyperparameter_search_{cobalt_mode}.csv", index=False)
    return best_params, search_df

def export_optimized(best_params: HyperParameters) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_summary = []
    all_stage = []
    all_transition = []
    all_coefficients = []
    for metal in METALS:
        optimized_inputs_by_year, transition_df, coefficient_df = optimize_metal_series(metal, best_params, cobalt_mode=DEFAULT_COBALT_MODE)
        if not transition_df.empty:
            all_transition.append(transition_df)
        if not coefficient_df.empty:
            all_coefficients.append(coefficient_df)
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
                {"best_params": asdict(best_params), "metal": metal, "optimization_version": "v4"},
            )
            all_summary.append(summary_df)
            all_stage.append(stage_summary(node_df))
    optimized_summary = pd.concat(all_summary, ignore_index=True)
    optimized_stage = pd.concat(all_stage, ignore_index=True)
    transition_detail = pd.concat(all_transition, ignore_index=True) if all_transition else pd.DataFrame()
    coefficient_detail = pd.concat(all_coefficients, ignore_index=True) if all_coefficients else pd.DataFrame()
    optimized_summary.to_csv(COMPARISON_OUTPUT_ROOT / "optimized_summary.csv", index=False)
    optimized_stage.to_csv(COMPARISON_OUTPUT_ROOT / "optimized_stage_summary.csv", index=False)
    transition_detail.to_csv(COMPARISON_OUTPUT_ROOT / "optimized_transition_detail.csv", index=False)
    coefficient_detail.to_csv(INTERMEDIATE_OUTPUT_ROOT / "v4_coefficients.csv", index=False)
    return optimized_summary, optimized_stage, transition_detail, coefficient_detail


def build_comparison_workbook(baseline_summary: pd.DataFrame, optimized_summary: pd.DataFrame, baseline_stage: pd.DataFrame, optimized_stage: pd.DataFrame, search_df: pd.DataFrame, transition_detail: pd.DataFrame, coefficient_detail: pd.DataFrame, best_params: HyperParameters) -> pd.DataFrame:
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
        coefficient_detail.to_excel(writer, sheet_name="coefficients", index=False)
        best_params_df.to_excel(writer, sheet_name="best_params", index=False)
    return comparison


def _build_feasibility_summary(comparison: pd.DataFrame, coefficient_detail: pd.DataFrame, best_params: HyperParameters) -> dict[str, Any]:
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
        "optimization_version": "v4",
        "shared_best_params": asdict(best_params),
        "best_params_by_metal": by_metal,
        "mean_unknown_reduction": float(comparison["unknown_reduction"].mean()),
        "median_unknown_reduction": float(comparison["unknown_reduction"].median()),
        "cases_improved": int((comparison["unknown_reduction"] > 0).sum()),
        "case_count": int(len(comparison)),
        "mean_bound_hit_rate": float((coefficient_detail["hit_lower"].sum() + coefficient_detail["hit_upper"].sum()) / len(coefficient_detail)) if not coefficient_detail.empty else 0.0,
    }


def _snapshot_v4_outputs() -> None:
    V4_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    output_snapshot = V4_SNAPSHOT_ROOT / "output"
    if output_snapshot.exists():
        shutil.rmtree(output_snapshot)
    shutil.copytree(OUTPUT_ROOT, output_snapshot)
    shutil.copy2(Path(__file__), V4_SNAPSHOT_ROOT / "pipeline_v4.py")
    config_path = Path(__file__).with_name("v4_config.py")
    if config_path.exists():
        shutil.copy2(config_path, V4_SNAPSHOT_ROOT / "v4_config.py")


def _build_version_comparison_v3_v4() -> pd.DataFrame | None:
    v3_comparison_path = V3_SNAPSHOT_ROOT / "output" / "comparison" / "comparison_summary.csv"
    current_comparison_path = COMPARISON_OUTPUT_ROOT / "comparison_summary.csv"
    if not v3_comparison_path.exists() or not current_comparison_path.exists():
        return None
    v3_comparison = pd.read_csv(v3_comparison_path)
    v4_comparison = pd.read_csv(current_comparison_path)
    merged = v3_comparison[["metal", "year", "unknown_reduction", "unknown_reduction_pct", "special_reduction"]].merge(
        v4_comparison[["metal", "year", "unknown_reduction", "unknown_reduction_pct", "special_reduction"]],
        on=["metal", "year"],
        suffixes=("_v3", "_v4"),
    )
    merged["unknown_reduction_delta_v4_minus_v3"] = merged["unknown_reduction_v4"] - merged["unknown_reduction_v3"]
    merged["special_reduction_delta_v4_minus_v3"] = merged["special_reduction_v4"] - merged["special_reduction_v3"]
    merged.to_csv(VERSION_OUTPUT_ROOT / "version_comparison_v3_v4.csv", index=False)
    return merged


def main() -> None:
    _ensure_output_dirs()
    baseline_summary, baseline_stage = export_baseline()
    v3.write_cobalt_baseline_variants(OUTPUT_ROOT, COMPARISON_OUTPUT_ROOT)
    best_params, search_df = run_shared_search()
    optimized_summary, optimized_stage, transition_detail, coefficient_detail = export_optimized(best_params)
    v3.export_cobalt_mode_variants(
        output_root=V3_SNAPSHOT_ROOT / "output",
        comparison_root=V3_SNAPSHOT_ROOT / "output" / "comparison",
        intermediate_root=V3_SNAPSHOT_ROOT / "output" / "intermediate",
        optimization_version="v3",
        coefficient_filename="v3_coefficients",
        search_fn=v3.run_cobalt_search,
        optimize_fn=v3.optimize_metal_series,
        graph_fn=v3.build_country_graph,
        baseline_output_root=BASELINE_OUTPUT_ROOT,
        baseline_comparison_root=COMPARISON_OUTPUT_ROOT,
    )
    v3.export_cobalt_mode_variants(
        output_root=OUTPUT_ROOT,
        comparison_root=COMPARISON_OUTPUT_ROOT,
        intermediate_root=INTERMEDIATE_OUTPUT_ROOT,
        optimization_version="v4",
        coefficient_filename="v4_coefficients",
        search_fn=run_cobalt_search,
        optimize_fn=optimize_metal_series,
        graph_fn=build_country_graph,
        baseline_output_root=BASELINE_OUTPUT_ROOT,
        baseline_comparison_root=COMPARISON_OUTPUT_ROOT,
    )
    comparison = build_comparison_workbook(baseline_summary, optimized_summary, baseline_stage, optimized_stage, search_df, transition_detail, coefficient_detail, best_params)
    result = _build_feasibility_summary(comparison, coefficient_detail, best_params)
    with (COMPARISON_OUTPUT_ROOT / "feasibility_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    _snapshot_v4_outputs()
    version_comparison = _build_version_comparison_v3_v4()
    if version_comparison is not None:
        result["version_comparison_rows"] = int(len(version_comparison))
        with (VERSION_OUTPUT_ROOT / "version_comparison_summary_v3_v4.json").open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mean_unknown_reduction_delta_v4_minus_v3": float(version_comparison["unknown_reduction_delta_v4_minus_v3"].mean()),
                    "median_unknown_reduction_delta_v4_minus_v3": float(version_comparison["unknown_reduction_delta_v4_minus_v3"].median()),
                    "cases_where_v4_improves_over_v3": int((version_comparison["unknown_reduction_delta_v4_minus_v3"] > 0).sum()),
                    "case_count": int(len(version_comparison)),
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
