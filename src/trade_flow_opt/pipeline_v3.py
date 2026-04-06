from __future__ import annotations

import json
import shutil
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from trade_flow_opt import pipeline_v1 as v1
from trade_flow_opt.v3_config import HS_ROLE_CONFIG, HSRoleSpec


# Paths / ·������
PROJECT_ROOT = v1.PROJECT_ROOT
OUTPUT_ROOT = v1.OUTPUT_ROOT
BASELINE_OUTPUT_ROOT = v1.BASELINE_OUTPUT_ROOT
OPTIMIZED_OUTPUT_ROOT = v1.OPTIMIZED_OUTPUT_ROOT
COMPARISON_OUTPUT_ROOT = v1.COMPARISON_OUTPUT_ROOT
SPREADSHEET_OUTPUT_ROOT = v1.SPREADSHEET_OUTPUT_ROOT
INTERMEDIATE_OUTPUT_ROOT = OUTPUT_ROOT / "intermediate"
VERSION_OUTPUT_ROOT = PROJECT_ROOT / "output_versions"
V1_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v1"
V2_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v2"
V3_SNAPSHOT_ROOT = VERSION_OUTPUT_ROOT / "v3"
COBALT_MODES = ("mid", "max", "min")
_write_case_mode_csvs = v1._write_case_mode_csvs

METALS = v1.METALS
YEARS = v1.YEARS
DEFAULT_COBALT_MODE = v1.DEFAULT_COBALT_MODE
EPSILON = v1.EPSILON

TransitionContext = v1.TransitionContext
TransitionSpec = v1.TransitionSpec
EdgeMap = v1.EdgeMap


@dataclass(frozen=True)
class HyperParameters:
    non_source_weight: float
    non_target_weight: float
    pp_penalty: float
    pn_up_penalty: float
    pn_down_penalty: float
    np_up_penalty: float
    np_down_penalty: float
    pp_smooth_penalty: float
    pn_smooth_penalty: float
    np_smooth_penalty: float
    coefficient_step: float
    coordinate_passes: int


HYPERPARAM_GRID = (
    HyperParameters(0.04, 0.04, 0.05, 0.20, 0.03, 0.22, 0.03, 0.04, 0.05, 0.05, 0.05, 1),
    HyperParameters(0.05, 0.05, 0.06, 0.24, 0.03, 0.26, 0.03, 0.05, 0.06, 0.06, 0.05, 1),
    HyperParameters(0.05, 0.05, 0.07, 0.28, 0.04, 0.30, 0.04, 0.07, 0.08, 0.08, 0.05, 2),
)


@dataclass(frozen=True)
class CoefficientKey:
    coefficient_class: str
    folder_name: str
    exporter: int | None = None
    importer: int | None = None

    def label(self) -> str:
        if self.coefficient_class == "PP":
            return f"{self.folder_name}|{self.exporter}->{self.importer}"
        if self.coefficient_class == "PN":
            return f"{self.folder_name}|{self.exporter}->non_target"
        if self.coefficient_class == "NP":
            return f"{self.folder_name}|non_source->{self.importer}"
        return f"{self.folder_name}|{self.coefficient_class}"


@dataclass
class FolderYearData:
    folder_name: str
    spec: HSRoleSpec
    raw_map: EdgeMap
    edge_classes: dict[tuple[int, int], str]
    source_producers: set[int]
    target_producers: set[int]
    exact_source_cap_map: dict[int, float]
    raw_total: float
    edge_count_by_class: dict[str, int]


@dataclass
class TransitionSeries:
    metal: str
    transition_spec: TransitionSpec
    context_by_year: dict[int, TransitionContext]
    folder_data_by_year: dict[int, dict[str, FolderYearData]]
    coefficient_meta: dict[CoefficientKey, dict[str, Any]]
    coefficient_order: list[CoefficientKey]
    exposure_by_key_year: dict[CoefficientKey, dict[int, float]]
    total_raw_by_year: dict[int, float]


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


def export_baseline() -> tuple[pd.DataFrame, pd.DataFrame]:
    return v1.export_baseline()


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


def _write_case_exports(root: Path, metal: str, year: int, scenario: str, inputs, nodes, links, extra_payload: dict[str, Any] | None = None):
    return v1._write_case_exports(root, metal, year, scenario, inputs, nodes, links, extra_payload)


def _write_case_variant(
    root: Path,
    metal: str,
    year: int,
    scenario: str,
    mode_suffix: str,
    inputs,
    nodes,
    links,
    extra_payload: dict[str, Any] | None = None,
):
    case_dir = root / metal / str(year)
    case_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{mode_suffix}" if mode_suffix else ""
    with (case_dir / f"{scenario}_inputs{suffix}.json").open("w", encoding="utf-8") as handle:
        json.dump(serialize_inputs(inputs), handle, ensure_ascii=False, indent=2)
    if extra_payload is not None:
        with (case_dir / f"{scenario}_payload{suffix}.json").open("w", encoding="utf-8") as handle:
            json.dump(extra_payload, handle, ensure_ascii=False, indent=2)
    return _write_case_mode_csvs(case_dir, metal, year, scenario, mode_suffix, nodes, links)


def _comparison_from_summaries(baseline_summary: pd.DataFrame, optimized_summary: pd.DataFrame) -> pd.DataFrame:
    comparison = baseline_summary.merge(optimized_summary, on=["metal", "year"], suffixes=("_baseline", "_optimized"))
    comparison["unknown_reduction"] = comparison["unknown_total_baseline"] - comparison["unknown_total_optimized"]
    comparison["unknown_reduction_pct"] = comparison["unknown_reduction"] / comparison["unknown_total_baseline"].replace(0, pd.NA)
    comparison["special_reduction"] = comparison["total_special_baseline"] - comparison["total_special_optimized"]
    return comparison


def write_cobalt_baseline_variants(output_root: Path, comparison_root: Path) -> dict[str, pd.DataFrame]:
    comparison_root.mkdir(parents=True, exist_ok=True)
    summaries_by_mode: dict[str, pd.DataFrame] = {}
    stages_by_mode: dict[str, pd.DataFrame] = {}
    for cobalt_mode in COBALT_MODES:
        mode_summaries: list[pd.DataFrame] = []
        mode_stages: list[pd.DataFrame] = []
        for year in YEARS:
            inputs = load_year_inputs("Co", year)
            payload = build_country_payload("Co", year, cobalt_mode=cobalt_mode)
            nodes, links = build_country_graph("Co", year, inputs=inputs, cobalt_mode=cobalt_mode)
            node_df, _link_df, summary_df = _write_case_variant(
                output_root / "baseline",
                "Co",
                year,
                "baseline",
                cobalt_mode,
                inputs,
                nodes,
                links,
                payload,
            )
            mode_summaries.append(summary_df)
            mode_stages.append(stage_summary(node_df))
        summary_frame = pd.concat(mode_summaries, ignore_index=True)
        stage_frame = pd.concat(mode_stages, ignore_index=True)
        summaries_by_mode[cobalt_mode] = summary_frame
        stages_by_mode[cobalt_mode] = stage_frame
        summary_frame.to_csv(comparison_root / f"baseline_summary_{cobalt_mode}.csv", index=False)
        stage_frame.to_csv(comparison_root / f"baseline_stage_summary_{cobalt_mode}.csv", index=False)
    return summaries_by_mode


def export_cobalt_mode_variants(
    *,
    output_root: Path,
    comparison_root: Path,
    intermediate_root: Path,
    optimization_version: str,
    coefficient_filename: str,
    search_fn,
    optimize_fn,
    graph_fn,
    baseline_output_root: Path = BASELINE_OUTPUT_ROOT,
    baseline_comparison_root: Path = COMPARISON_OUTPUT_ROOT,
) -> dict[str, Any]:
    comparison_root.mkdir(parents=True, exist_ok=True)
    intermediate_root.mkdir(parents=True, exist_ok=True)
    baseline_summaries: dict[str, pd.DataFrame] = {}
    for cobalt_mode in COBALT_MODES:
        baseline_path = baseline_comparison_root / f"baseline_summary_{cobalt_mode}.csv"
        if baseline_path.exists():
            baseline_summaries[cobalt_mode] = pd.read_csv(baseline_path)
            continue
        rows: list[pd.DataFrame] = []
        for year in YEARS:
            summary_path = baseline_output_root / "Co" / str(year) / f"baseline_summary_{cobalt_mode}.csv"
            if summary_path.exists():
                rows.append(pd.read_csv(summary_path))
        baseline_summaries[cobalt_mode] = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    mode_results: dict[str, Any] = {}
    for cobalt_mode in COBALT_MODES:
        best_params, search_df = search_fn(cobalt_mode=cobalt_mode, write_search_csv=False)
        optimized_inputs_by_year, transition_df, coefficient_df = optimize_fn("Co", best_params, cobalt_mode=cobalt_mode)
        summary_rows: list[pd.DataFrame] = []
        stage_rows: list[pd.DataFrame] = []
        for year in YEARS:
            optimized_inputs = optimized_inputs_by_year[year]
            nodes, links = graph_fn("Co", year, inputs=optimized_inputs, cobalt_mode=cobalt_mode)
            node_df, _link_df, summary_df = _write_case_variant(
                output_root / "optimized",
                "Co",
                year,
                "optimized",
                cobalt_mode,
                optimized_inputs,
                nodes,
                links,
                {
                    "best_params": asdict(best_params),
                    "metal": "Co",
                    "optimization_version": optimization_version,
                    "cobalt_mode": cobalt_mode,
                },
            )
            summary_rows.append(summary_df)
            stage_rows.append(stage_summary(node_df))

        optimized_summary = pd.concat(summary_rows, ignore_index=True)
        optimized_stage = pd.concat(stage_rows, ignore_index=True)
        optimized_summary.to_csv(comparison_root / f"optimized_summary_{cobalt_mode}.csv", index=False)
        optimized_stage.to_csv(comparison_root / f"optimized_stage_summary_{cobalt_mode}.csv", index=False)
        transition_df.to_csv(comparison_root / f"optimized_transition_detail_{cobalt_mode}.csv", index=False)
        coefficient_df.to_csv(intermediate_root / f"{coefficient_filename}_{cobalt_mode}.csv", index=False)
        search_df.to_csv(comparison_root / f"hyperparameter_search_{cobalt_mode}.csv", index=False)

        baseline_summary = baseline_summaries.get(cobalt_mode, pd.DataFrame())
        comparison = _comparison_from_summaries(baseline_summary, optimized_summary) if not baseline_summary.empty else pd.DataFrame()
        if not comparison.empty:
            comparison.to_csv(comparison_root / f"comparison_summary_{cobalt_mode}.csv", index=False)
        mode_results[cobalt_mode] = {
            "best_params": asdict(best_params),
            "best_score": float(search_df.iloc[0]["score"]),
            "cases_improved": int((comparison["unknown_reduction"] > 0).sum()) if not comparison.empty else 0,
            "case_count": int(len(comparison)),
            "unknown_reduction_total": float(comparison["unknown_reduction"].sum()) if not comparison.empty else 0.0,
            "mean_bound_hit_rate": float((coefficient_df["hit_lower"].sum() + coefficient_df["hit_upper"].sum()) / len(coefficient_df))
            if not coefficient_df.empty
            else 0.0,
        }

    with (comparison_root / "cobalt_mode_results.json").open("w", encoding="utf-8") as handle:
        json.dump(mode_results, handle, ensure_ascii=False, indent=2)
    return mode_results


def _merge_maps(*maps: EdgeMap) -> EdgeMap:
    return v1._merge_edge_maps(*maps)


def _sum_maps(*maps: dict[int, float]) -> dict[int, float]:
    return v1._sum_maps(*maps)


def _nonzero_country_set(mapping: dict[int, float]) -> set[int]:
    return {int(country_id) for country_id, value in mapping.items() if abs(float(value)) > EPSILON}


def _map_from_fields(inputs, field_names: tuple[str, ...]) -> dict[int, float]:
    if not field_names:
        return {}
    return _sum_maps(*(dict(getattr(inputs, field_name, {})) for field_name in field_names))


def _classify_edge(exporter: int, importer: int, source_producers: set[int], target_producers: set[int]) -> str:
    if exporter in source_producers and importer in target_producers:
        return "PP"
    if exporter in source_producers and importer not in target_producers:
        return "PN"
    if exporter not in source_producers and importer in target_producers:
        return "NP"
    return "NN"


def _coefficient_key(folder_name: str, edge_class: str, exporter: int, importer: int) -> CoefficientKey | None:
    if edge_class == "PP":
        return CoefficientKey("PP", folder_name, exporter=exporter, importer=importer)
    if edge_class == "PN":
        return CoefficientKey("PN", folder_name, exporter=exporter)
    if edge_class == "NP":
        return CoefficientKey("NP", folder_name, importer=importer)
    return None


def _build_grid(lower: float, upper: float, step: float) -> list[float]:
    values: list[float] = []
    current = lower
    while current <= upper + 1e-9:
        values.append(round(current, 6))
        current += step
    for anchor in (lower, 1.0, upper):
        if lower - 1e-9 <= anchor <= upper + 1e-9:
            values.append(round(anchor, 6))
    return sorted(set(values))


def _coefficient_grid(spec: HSRoleSpec, coefficient_class: str, step: float) -> list[float]:
    if coefficient_class == "PP":
        return _build_grid(1.0, float(spec.pp_upper), step)
    if coefficient_class == "PN":
        return _build_grid(float(spec.pn_lower), float(spec.pn_upper), step)
    if coefficient_class == "NP":
        return _build_grid(float(spec.np_lower), float(spec.np_upper), step)
    return [1.0]


def _coefficient_bounds(spec: HSRoleSpec, coefficient_class: str) -> tuple[float, float]:
    if coefficient_class == "PP":
        return 1.0, float(spec.pp_upper)
    if coefficient_class == "PN":
        return float(spec.pn_lower), float(spec.pn_upper)
    if coefficient_class == "NP":
        return float(spec.np_lower), float(spec.np_upper)
    return 1.0, 1.0


def _coefficient_delta(spec: HSRoleSpec, coefficient_class: str) -> float:
    if coefficient_class == "PP":
        return float(spec.pp_delta)
    if coefficient_class == "PN":
        return float(spec.pn_delta)
    if coefficient_class == "NP":
        return float(spec.np_delta)
    return 0.0


def _regularization_cost(coefficient_class: str, value: float, exposure_share: float, params: HyperParameters) -> float:
    if coefficient_class == "PP":
        return params.pp_penalty * exposure_share * abs(float(value) - 1.0)
    if coefficient_class == "PN":
        return exposure_share * (
            params.pn_up_penalty * max(float(value) - 1.0, 0.0)
            + params.pn_down_penalty * max(1.0 - float(value), 0.0)
        )
    if coefficient_class == "NP":
        return exposure_share * (
            params.np_up_penalty * max(float(value) - 1.0, 0.0)
            + params.np_down_penalty * max(1.0 - float(value), 0.0)
        )
    return 0.0


def _smooth_penalty(coefficient_class: str, delta: float, exposure_weight: float, params: HyperParameters) -> float:
    if coefficient_class == "PP":
        return params.pp_smooth_penalty * exposure_weight * delta
    if coefficient_class == "PN":
        return params.pn_smooth_penalty * exposure_weight * delta
    if coefficient_class == "NP":
        return params.np_smooth_penalty * exposure_weight * delta
    return 0.0


def _source_cap_map(folder_data: FolderYearData, context: TransitionContext) -> dict[int, float]:
    if folder_data.spec.exact_source_cap_fields:
        return dict(folder_data.exact_source_cap_map)
    if folder_data.spec.use_transition_supply_cap:
        return {int(k): float(v) for k, v in context.trade_supply.items()}
    return {}


def _build_folder_year_data(
    metal: str,
    year: int,
    folder_name: str,
    inputs,
    context: TransitionContext,
) -> FolderYearData:
    del metal
    spec = HS_ROLE_CONFIG[folder_name]
    raw_map = v1.load_trade_folder(folder_name, year, "import") if spec.optimize else {}
    source_map = _map_from_fields(inputs, spec.source_fields)
    target_map = _map_from_fields(inputs, spec.target_fields)
    source_producers = _nonzero_country_set(source_map)
    target_producers = _nonzero_country_set(target_map)
    exact_source_cap_map = _map_from_fields(inputs, spec.exact_source_cap_fields)

    edge_classes: dict[tuple[int, int], str] = {}
    edge_count_by_class: dict[str, int] = {"PP": 0, "PN": 0, "NP": 0, "NN": 0}
    for edge, value in raw_map.items():
        if value <= EPSILON:
            continue
        edge_class = _classify_edge(edge[0], edge[1], source_producers, target_producers)
        edge_classes[edge] = edge_class
        edge_count_by_class[edge_class] += 1

    return FolderYearData(
        folder_name=folder_name,
        spec=spec,
        raw_map=raw_map,
        edge_classes=edge_classes,
        source_producers=source_producers,
        target_producers=target_producers,
        exact_source_cap_map=exact_source_cap_map,
        raw_total=float(sum(raw_map.values())),
        edge_count_by_class=edge_count_by_class,
    )


def _build_transition_series(
    metal: str,
    transition_spec: TransitionSpec,
    base_inputs_by_year: dict[int, Any],
    contexts_by_year: dict[int, dict[str, TransitionContext]],
) -> TransitionSeries:
    context_by_year = {year: contexts_by_year[year][transition_spec.key] for year in YEARS}
    folder_data_by_year: dict[int, dict[str, FolderYearData]] = {}
    coefficient_meta: dict[CoefficientKey, dict[str, Any]] = {}
    exposure_by_key_year: dict[CoefficientKey, dict[int, float]] = defaultdict(dict)
    total_raw_by_year: dict[int, float] = {}

    for year in YEARS:
        context = context_by_year[year]
        inputs = base_inputs_by_year[year]
        folder_data_by_year[year] = {}
        total_raw = 0.0
        for folder_name in transition_spec.folder_names:
            folder_year = _build_folder_year_data(metal, year, folder_name, inputs, context)
            folder_data_by_year[year][folder_name] = folder_year
            total_raw += folder_year.raw_total
            if not folder_year.spec.optimize:
                continue
            for edge, value in folder_year.raw_map.items():
                if value <= EPSILON:
                    continue
                edge_class = folder_year.edge_classes[edge]
                coefficient_key = _coefficient_key(folder_name, edge_class, edge[0], edge[1])
                if coefficient_key is None:
                    continue
                exposure_by_key_year[coefficient_key][year] = exposure_by_key_year[coefficient_key].get(year, 0.0) + float(value)
                if coefficient_key not in coefficient_meta:
                    coefficient_meta[coefficient_key] = {
                        "class": edge_class,
                        "folder_name": folder_name,
                        "spec": folder_year.spec,
                        "exporter": coefficient_key.exporter,
                        "importer": coefficient_key.importer,
                    }
        total_raw_by_year[year] = total_raw

    def sort_key(key: CoefficientKey) -> tuple[int, float, str]:
        class_order = {"PP": 0, "PN": 1, "NP": 2}
        total_exposure = -float(sum(exposure_by_key_year[key].values()))
        return class_order.get(key.coefficient_class, 99), total_exposure, key.label()

    coefficient_order = sorted(coefficient_meta, key=sort_key)
    return TransitionSeries(
        metal=metal,
        transition_spec=transition_spec,
        context_by_year=context_by_year,
        folder_data_by_year=folder_data_by_year,
        coefficient_meta=coefficient_meta,
        coefficient_order=coefficient_order,
        exposure_by_key_year={key: dict(value) for key, value in exposure_by_key_year.items()},
        total_raw_by_year=total_raw_by_year,
    )

def _build_year_folder_maps(
    series: TransitionSeries,
    year: int,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
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
        outgoing = v1._country_outgoing(folder_maps.get(folder_name, {}))
        for exporter in folder_data.source_producers:
            total_out = float(outgoing.get(exporter, 0.0))
            cap = float(cap_map.get(exporter, 0.0))
            if total_out <= cap + EPSILON:
                continue
            scale = cap / total_out if cap > EPSILON else 0.0
            for edge in list(folder_maps.get(folder_name, {})):
                if edge[0] != exporter:
                    continue
                scaled = folder_maps[folder_name][edge] * scale
                if scaled > EPSILON:
                    folder_maps[folder_name][edge] = scaled
                else:
                    folder_maps[folder_name].pop(edge, None)

    shared_folders = [
        folder_name
        for folder_name, folder_data in year_folder_data.items()
        if folder_data.spec.optimize and folder_data.spec.use_transition_supply_cap
    ]
    if shared_folders:
        shared_exporters: set[int] = set()
        combined_outgoing: dict[int, float] = defaultdict(float)
        for folder_name in shared_folders:
            folder_data = year_folder_data[folder_name]
            shared_exporters.update(folder_data.source_producers)
            for exporter, total_out in v1._country_outgoing(folder_maps.get(folder_name, {})).items():
                combined_outgoing[exporter] += float(total_out)
        for exporter in shared_exporters:
            total_out = float(combined_outgoing.get(exporter, 0.0))
            cap = float(context.trade_supply.get(exporter, 0.0))
            if total_out <= cap + EPSILON:
                continue
            scale = cap / total_out if cap > EPSILON else 0.0
            for folder_name in shared_folders:
                folder_map = folder_maps.get(folder_name, {})
                for edge in list(folder_map):
                    if edge[0] != exporter:
                        continue
                    scaled = folder_map[edge] * scale
                    if scaled > EPSILON:
                        folder_map[edge] = scaled
                    else:
                        folder_map.pop(edge, None)

    return {folder_name: {edge: value for edge, value in folder_map.items() if value > EPSILON} for folder_name, folder_map in folder_maps.items()}


def _evaluate_transition_year(
    series: TransitionSeries,
    year: int,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    override: tuple[CoefficientKey, float] | None = None,
) -> tuple[dict[str, float], dict[str, EdgeMap]]:
    folder_maps = _build_year_folder_maps(series, year, coefficient_paths, override=override)
    combined_map = _merge_maps(*folder_maps.values()) if folder_maps else {}
    metrics = v1.evaluate_transition(combined_map, series.context_by_year[year])
    return metrics, folder_maps


def _base_residual_cost(metrics: dict[str, float], params: HyperParameters) -> float:
    return (
        float(metrics["unknown_total"])
        + params.non_source_weight * float(metrics["non_source_total"])
        + params.non_target_weight * float(metrics["non_target_total"])
    )


def _exposure_share(series: TransitionSeries, coefficient_key: CoefficientKey, year: int) -> float:
    exposure = float(series.exposure_by_key_year.get(coefficient_key, {}).get(year, 0.0))
    total = float(series.total_raw_by_year.get(year, 0.0))
    if total <= EPSILON or exposure <= EPSILON:
        return 0.0
    return exposure / total


def _local_year_cost(
    series: TransitionSeries,
    year: int,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    coefficient_key: CoefficientKey,
    candidate_value: float,
    params: HyperParameters,
) -> float:
    metrics, _folder_maps = _evaluate_transition_year(series, year, coefficient_paths, override=(coefficient_key, candidate_value))
    residual_cost = _base_residual_cost(metrics, params)
    exposure_share = _exposure_share(series, coefficient_key, year)
    regularization_cost = _regularization_cost(
        coefficient_key.coefficient_class,
        candidate_value,
        exposure_share,
        params,
    )
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
        local_costs[year] = {
            value: _local_year_cost(series, year, coefficient_paths, coefficient_key, value, params) for value in values
        }

    states: dict[float, float] = {value: local_costs[YEARS[0]][value] for value in values}
    backtrack: dict[tuple[int, float], float | None] = {(0, value): None for value in values}

    for index, year in enumerate(YEARS[1:], start=1):
        previous_year = YEARS[index - 1]
        next_states: dict[float, float] = {}
        for value in values:
            best_cost: float | None = None
            best_previous: float | None = None
            for previous_value, previous_cost in states.items():
                transition_cost = _transition_cost(
                    series,
                    coefficient_key,
                    previous_year,
                    year,
                    previous_value,
                    value,
                    params,
                )
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


def _folder_coefficient_summary(
    series: TransitionSeries,
    coefficient_paths: dict[CoefficientKey, dict[int, float]],
    folder_name: str,
    year: int,
) -> tuple[dict[str, float], int]:
    pairs: list[tuple[float, str, float]] = []
    hit_count = 0
    for coefficient_key, meta in series.coefficient_meta.items():
        if meta["folder_name"] != folder_name:
            continue
        value = float(coefficient_paths[coefficient_key][year])
        lower, upper = _coefficient_bounds(meta["spec"], coefficient_key.coefficient_class)
        if abs(value - lower) <= 1e-9 or abs(value - upper) <= 1e-9:
            hit_count += 1
        exposure = float(series.exposure_by_key_year.get(coefficient_key, {}).get(year, 0.0))
        if exposure <= EPSILON:
            continue
        pairs.append((exposure, coefficient_key.label(), value))
    pairs.sort(reverse=True)
    summary = {label: value for _exposure, label, value in pairs[:12]}
    return summary, hit_count


def optimize_transition_series_v3(
    series: TransitionSeries,
    params: HyperParameters,
) -> tuple[dict[int, dict[str, EdgeMap]], pd.DataFrame, pd.DataFrame]:
    if not any(folder_data.spec.optimize for folder_map in series.folder_data_by_year.values() for folder_data in folder_map.values()):
        rows = [
            {
                "metal": series.metal,
                "year": year,
                "transition": series.transition_spec.key,
                "folder_name": folder_name,
                "optimize_enabled": False,
                "skipped_reason": HS_ROLE_CONFIG[folder_name].note or "Synthetic / non-Comtrade bucket",
                "stage_unknown_total": 0.0,
                "non_source_total": 0.0,
                "non_target_total": 0.0,
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
        metrics, folder_maps = _evaluate_transition_year(series, year, coefficient_paths)
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
                    "stage_unknown_total": float(metrics["unknown_total"]),
                    "non_source_total": float(metrics["non_source_total"]),
                    "non_target_total": float(metrics["non_target_total"]),
                    "folder_raw_total": float(folder_data.raw_total),
                    "folder_optimized_total": float(sum(folder_maps.get(folder_name, {}).values())),
                    "pp_edge_count": int(folder_data.edge_count_by_class["PP"]),
                    "pn_edge_count": int(folder_data.edge_count_by_class["PN"]),
                    "np_edge_count": int(folder_data.edge_count_by_class["NP"]),
                    "nn_edge_count": int(folder_data.edge_count_by_class["NN"]),
                    "source_producer_count": int(len(folder_data.source_producers)),
                    "target_producer_count": int(len(folder_data.target_producers)),
                    "coefficient_count": int(
                        sum(
                            1
                            for coefficient_key, meta in series.coefficient_meta.items()
                            if meta["folder_name"] == folder_name and float(series.exposure_by_key_year.get(coefficient_key, {}).get(year, 0.0)) > EPSILON
                        )
                    ),
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


def optimize_metal_series(
    metal: str,
    params: HyperParameters,
    *,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
) -> tuple[dict[int, Any], pd.DataFrame, pd.DataFrame]:
    base_inputs_by_year = {year: load_year_inputs(metal, year) for year in YEARS}
    contexts_by_year = {
        year: transition_contexts(metal, base_inputs_by_year[year], cobalt_mode=cobalt_mode) for year in YEARS
    }
    replacement_field_maps_by_year: dict[int, dict[str, EdgeMap]] = {year: {} for year in YEARS}
    transition_frames: list[pd.DataFrame] = []
    coefficient_frames: list[pd.DataFrame] = []

    for transition_spec in v1.TRANSITIONS_BY_METAL[metal]:
        series = _build_transition_series(metal, transition_spec, base_inputs_by_year, contexts_by_year)
        folder_maps_by_year, transition_df, coefficient_df = optimize_transition_series_v3(series, params)
        if not transition_df.empty:
            transition_frames.append(transition_df)
        if not coefficient_df.empty:
            coefficient_frames.append(coefficient_df)

        optimize_folders = {
            folder_name
            for folder_name in transition_spec.folder_names
            if HS_ROLE_CONFIG[folder_name].optimize
        }
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

    optimized_inputs_by_year = {
        year: replace_trade_fields(metal, base_inputs_by_year[year], replacement_field_maps_by_year[year]) for year in YEARS
    }
    transition_detail = pd.concat(transition_frames, ignore_index=True) if transition_frames else pd.DataFrame()
    coefficient_detail = pd.concat(coefficient_frames, ignore_index=True) if coefficient_frames else pd.DataFrame()
    return optimized_inputs_by_year, transition_detail, coefficient_detail


def run_shared_search(*, cobalt_mode: str = DEFAULT_COBALT_MODE, write_search_csv: bool = True) -> tuple[HyperParameters, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    best_params: HyperParameters | None = None
    best_score: float | None = None

    for params in HYPERPARAM_GRID:
        total_unknown = 0.0
        total_special = 0.0
        total_non_source = 0.0
        total_non_target = 0.0
        total_bound_hits = 0
        total_coefficients = 0
        metal_unknowns: dict[str, float] = {}

        for metal in METALS:
            optimized_inputs_by_year, _transition_df, coefficient_df = optimize_metal_series(metal, params, cobalt_mode=cobalt_mode)
            metal_unknown = 0.0
            for year in YEARS:
                nodes, links = build_country_graph(
                    metal,
                    year,
                    inputs=optimized_inputs_by_year[year],
                    cobalt_mode=cobalt_mode,
                )
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
        score = (
            total_unknown
            + 0.02 * total_special
            + 0.01 * (total_non_source + total_non_target)
            + 500.0 * bound_hit_rate
        )
        rows.append(
            {
                **asdict(params),
                "score": score,
                "unknown_total": total_unknown,
                "total_special": total_special,
                "non_source_total": total_non_source,
                "non_target_total": total_non_target,
                "bound_hit_rate": bound_hit_rate,
                "Li_unknown_total": metal_unknowns["Li"],
                "Ni_unknown_total": metal_unknowns["Ni"],
                "Co_unknown_total": metal_unknowns["Co"],
            }
        )
        if best_score is None or score < best_score:
            best_score = score
            best_params = params

    if best_params is None:
        raise RuntimeError("No V3 hyperparameter result was produced.")
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
        raise RuntimeError("No V3 cobalt hyperparameter result was produced.")
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
                {"best_params": asdict(best_params), "metal": metal, "optimization_version": "v3"},
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
    coefficient_detail.to_csv(INTERMEDIATE_OUTPUT_ROOT / "v3_coefficients.csv", index=False)
    return optimized_summary, optimized_stage, transition_detail, coefficient_detail

def build_comparison_workbook(
    baseline_summary: pd.DataFrame,
    optimized_summary: pd.DataFrame,
    baseline_stage: pd.DataFrame,
    optimized_stage: pd.DataFrame,
    search_df: pd.DataFrame,
    transition_detail: pd.DataFrame,
    coefficient_detail: pd.DataFrame,
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
        coefficient_detail.to_excel(writer, sheet_name="coefficients", index=False)
        best_params_df.to_excel(writer, sheet_name="best_params", index=False)
    return comparison


def _build_feasibility_summary(
    comparison: pd.DataFrame,
    coefficient_detail: pd.DataFrame,
    best_params: HyperParameters,
) -> dict[str, Any]:
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
        "optimization_version": "v3",
        "shared_best_params": asdict(best_params),
        "best_params_by_metal": by_metal,
        "mean_unknown_reduction": float(comparison["unknown_reduction"].mean()),
        "median_unknown_reduction": float(comparison["unknown_reduction"].median()),
        "cases_improved": int((comparison["unknown_reduction"] > 0).sum()),
        "case_count": int(len(comparison)),
        "mean_bound_hit_rate": float(
            (coefficient_detail["hit_lower"].sum() + coefficient_detail["hit_upper"].sum()) / len(coefficient_detail)
        )
        if not coefficient_detail.empty
        else 0.0,
    }


def _snapshot_v3_outputs() -> None:
    V3_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    output_snapshot = V3_SNAPSHOT_ROOT / "output"
    if output_snapshot.exists():
        shutil.rmtree(output_snapshot)
    shutil.copytree(OUTPUT_ROOT, output_snapshot)
    shutil.copy2(Path(__file__), V3_SNAPSHOT_ROOT / "pipeline_v3.py")


def _build_version_comparison_v2_v3() -> pd.DataFrame | None:
    v2_comparison_path = V2_SNAPSHOT_ROOT / "output" / "comparison" / "comparison_summary.csv"
    current_comparison_path = COMPARISON_OUTPUT_ROOT / "comparison_summary.csv"
    if not v2_comparison_path.exists() or not current_comparison_path.exists():
        return None
    v2_comparison = pd.read_csv(v2_comparison_path)
    v3_comparison = pd.read_csv(current_comparison_path)
    merged = v2_comparison[
        ["metal", "year", "unknown_reduction", "unknown_reduction_pct", "special_reduction"]
    ].merge(
        v3_comparison[["metal", "year", "unknown_reduction", "unknown_reduction_pct", "special_reduction"]],
        on=["metal", "year"],
        suffixes=("_v2", "_v3"),
    )
    merged["unknown_reduction_delta_v3_minus_v2"] = (
        merged["unknown_reduction_v3"] - merged["unknown_reduction_v2"]
    )
    merged["special_reduction_delta_v3_minus_v2"] = (
        merged["special_reduction_v3"] - merged["special_reduction_v2"]
    )
    merged.to_csv(VERSION_OUTPUT_ROOT / "version_comparison_v2_v3.csv", index=False)
    return merged


def main() -> None:
    _ensure_output_dirs()
    baseline_summary, baseline_stage = export_baseline()
    write_cobalt_baseline_variants(OUTPUT_ROOT, COMPARISON_OUTPUT_ROOT)
    best_params, search_df = run_shared_search()
    optimized_summary, optimized_stage, transition_detail, coefficient_detail = export_optimized(best_params)
    export_cobalt_mode_variants(
        output_root=OUTPUT_ROOT,
        comparison_root=COMPARISON_OUTPUT_ROOT,
        intermediate_root=INTERMEDIATE_OUTPUT_ROOT,
        optimization_version="v3",
        coefficient_filename="v3_coefficients",
        search_fn=run_cobalt_search,
        optimize_fn=optimize_metal_series,
        graph_fn=build_country_graph,
    )
    comparison = build_comparison_workbook(
        baseline_summary,
        optimized_summary,
        baseline_stage,
        optimized_stage,
        search_df,
        transition_detail,
        coefficient_detail,
        best_params,
    )
    result = _build_feasibility_summary(comparison, coefficient_detail, best_params)
    with (COMPARISON_OUTPUT_ROOT / "feasibility_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    _snapshot_v3_outputs()
    version_comparison = _build_version_comparison_v2_v3()
    if version_comparison is not None:
        result["version_comparison_rows"] = int(len(version_comparison))
        with (VERSION_OUTPUT_ROOT / "version_comparison_summary_v2_v3.json").open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mean_unknown_reduction_delta_v3_minus_v2": float(
                        version_comparison["unknown_reduction_delta_v3_minus_v2"].mean()
                    ),
                    "median_unknown_reduction_delta_v3_minus_v2": float(
                        version_comparison["unknown_reduction_delta_v3_minus_v2"].median()
                    ),
                    "cases_where_v3_improves_over_v2": int(
                        (version_comparison["unknown_reduction_delta_v3_minus_v2"] > 0).sum()
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
