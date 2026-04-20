from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from trade_flow.baseline import pipeline_v1
from trade_flow.common.paths import get_project_paths
from trade_flow.conversion_factor_optimization import conversion_factor_optimizer
from trade_flow.conversion_factor_optimization.role_config import HS_ROLE_CONFIG


EPSILON = 1e-9
DEFAULT_STAGE_FOLDER_NAMES = {
    ("S1", "S2", "S3"): "s1_s2_s3",
    ("S3", "S4", "S5"): "s3_s4_s5",
    ("S5", "S6", "S7"): "s5_s6_s7",
}


def _candidate_website_root(explicit_root: str | Path | None = None) -> Path:
    if explicit_root is not None:
        return Path(explicit_root).resolve()
    return Path(__file__).resolve().parents[3]


def _resolve_project_root(explicit_root: str | Path | None = None) -> Path:
    candidate = _candidate_website_root(explicit_root)
    return candidate.resolve()


def _load_conversion_factor_optimization_module() -> Any:
    return conversion_factor_optimizer


def _sum_maps(*mappings: dict[int, float]) -> dict[int, float]:
    merged: dict[int, float] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            numeric_key = int(key)
            merged[numeric_key] = merged.get(numeric_key, 0.0) + float(value)
    return {key: value for key, value in merged.items() if abs(value) > EPSILON}


def _map_from_fields(inputs: Any, field_names: tuple[str, ...]) -> dict[int, float]:
    if not field_names:
        return {}
    return _sum_maps(*(dict(getattr(inputs, field_name, {})) for field_name in field_names))


def _nonzero_country_set(mapping: dict[int, float]) -> set[int]:
    return {int(country_id) for country_id, value in mapping.items() if abs(float(value)) > EPSILON}


def _merge_edge_maps(*maps: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    merged: dict[tuple[int, int], float] = defaultdict(float)
    for edge_map in maps:
        for edge, value in edge_map.items():
            if abs(float(value)) <= EPSILON:
                continue
            merged[(int(edge[0]), int(edge[1]))] += float(value)
    return {edge: value for edge, value in merged.items() if value > EPSILON}


def _stage_slug(transition_spec: Any) -> str:
    key = (
        str(transition_spec.source_stage).upper(),
        str(transition_spec.post_stage).upper(),
        str(transition_spec.target_stage).upper(),
    )
    if key in DEFAULT_STAGE_FOLDER_NAMES:
        return DEFAULT_STAGE_FOLDER_NAMES[key]
    return "_".join(stage.lower() for stage in key)


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_factor_tables(case_dir: Path) -> dict[str, dict[Any, float]]:
    factor_specs = {
        "A": ("factor_A.csv", ("folder_name", "source_country_id", "target_country_id"), "optimized_A_ij"),
        "B": ("factor_B.csv", ("folder_name", "source_country_id"), "optimized_B_i"),
        "G": ("factor_G.csv", ("folder_name", "target_country_id"), "optimized_G_j"),
        "NN": ("factor_NN.csv", ("folder_name", "source_country_id"), "optimized_NN_i"),
    }
    tables: dict[str, dict[Any, float]] = {}
    for factor_name, (filename, key_columns, value_column) in factor_specs.items():
        path = case_dir / filename
        if not path.exists():
            tables[factor_name] = {}
            continue
        frame = pd.read_csv(path).fillna("")
        lookup: dict[Any, float] = {}
        for record in frame.to_dict(orient="records"):
            raw_key = [str(record.get(key_columns[0], "")).strip()]
            raw_key.extend(_safe_int(record.get(column)) for column in key_columns[1:])
            lookup[tuple(raw_key)] = _safe_float(record.get(value_column))
        tables[factor_name] = lookup
    return tables


def _build_folder_flow_map(
    *,
    folder_name: str,
    hs_code: str,
    raw_import_root: Path,
    year: int,
    source_countries: set[int],
    target_countries: set[int],
    factor_tables: dict[str, dict[Any, float]],
    recommended_factor: float,
    optimizer_module: Any,
) -> dict[tuple[int, int], float]:
    raw_map = optimizer_module._load_raw_import_map(raw_import_root, year, hs_code)
    flow_map: dict[tuple[int, int], float] = {}
    a_lookup = factor_tables["A"]
    b_lookup = factor_tables["B"]
    g_lookup = factor_tables["G"]
    nn_lookup = factor_tables["NN"]

    for (exporter, importer), quantity in raw_map.items():
        if quantity <= EPSILON:
            continue
        edge = (int(exporter), int(importer))
        coefficient = None
        if exporter in source_countries and importer in target_countries:
            coefficient = a_lookup.get((folder_name, int(exporter), int(importer)), recommended_factor)
        elif exporter in source_countries and importer not in target_countries:
            coefficient = b_lookup.get((folder_name, int(exporter)), recommended_factor)
        elif exporter not in source_countries and importer in target_countries:
            coefficient = g_lookup.get((folder_name, int(importer)), recommended_factor)
        elif exporter not in source_countries and exporter in target_countries and importer not in target_countries:
            coefficient = nn_lookup.get((folder_name, int(exporter)), recommended_factor)
        if coefficient is None:
            continue
        adjusted_value = float(quantity) * float(coefficient)
        if adjusted_value > EPSILON:
            flow_map[edge] = adjusted_value
    return flow_map


def _build_replacement_field_maps_for_case(
    *,
    metal: str,
    year: int,
    inputs: Any,
    transition_spec: Any,
    optimizer_module: Any,
    raw_import_root: Path,
    case_dir: Path,
) -> dict[str, dict[tuple[int, int], float]]:
    if not case_dir.exists():
        return {}
    factor_tables = _load_factor_tables(case_dir)
    per_folder_maps: dict[str, dict[tuple[int, int], float]] = {}
    for folder_name in transition_spec.folder_names:
        theoretical = optimizer_module.FOLDER_THEORETICAL_CONFIG.get(folder_name)
        role_spec = HS_ROLE_CONFIG.get(folder_name)
        if theoretical is None or role_spec is None or not role_spec.optimize:
            continue
        if theoretical.unsupported_reason or theoretical.hs_code is None:
            continue
        source_map = _map_from_fields(inputs, tuple(role_spec.source_fields))
        target_map = _map_from_fields(inputs, tuple(role_spec.target_fields))
        source_countries = _nonzero_country_set(source_map)
        target_countries = _nonzero_country_set(target_map)
        per_folder_maps[folder_name] = _build_folder_flow_map(
            folder_name=folder_name,
            hs_code=str(theoretical.hs_code),
            raw_import_root=raw_import_root,
            year=year,
            source_countries=source_countries,
            target_countries=target_countries,
            factor_tables=factor_tables,
            recommended_factor=float(theoretical.crec),
            optimizer_module=optimizer_module,
        )

    if not per_folder_maps:
        return {}
    if len(transition_spec.input_fields) == 1:
        return {transition_spec.input_fields[0]: _merge_edge_maps(*per_folder_maps.values())}
    return {
        field_name: per_folder_maps[folder_name]
        for field_name, folder_name in zip(transition_spec.input_fields, transition_spec.folder_names)
        if folder_name in per_folder_maps
    }


def build_optimized_inputs_by_year(
    *,
    metal: str,
    conversion_factor_optimization_root: Path,
    raw_import_root: Path,
) -> tuple[dict[int, Any], list[dict[str, Any]]]:
    optimizer_module = _load_conversion_factor_optimization_module()

    optimized_inputs_by_year: dict[int, Any] = {}
    transformed_cases: list[dict[str, Any]] = []
    optimization_output_root = conversion_factor_optimization_root / "output"

    for year in pipeline_v1.YEARS:
        inputs = pipeline_v1.load_year_inputs(metal, year)
        replacement_field_maps: dict[str, dict[tuple[int, int], float]] = {}
        applied_transition_slugs: list[str] = []

        for transition_spec in pipeline_v1.TRANSITIONS_BY_METAL[metal]:
            stage_slug = _stage_slug(transition_spec)
            case_dir = optimization_output_root / metal / str(year) / stage_slug
            case_field_maps = _build_replacement_field_maps_for_case(
                metal=metal,
                year=year,
                inputs=inputs,
                transition_spec=transition_spec,
                optimizer_module=optimizer_module,
                raw_import_root=raw_import_root,
                case_dir=case_dir,
            )
            if not case_field_maps:
                continue
            replacement_field_maps.update(case_field_maps)
            applied_transition_slugs.append(stage_slug)

        optimized_inputs = pipeline_v1.replace_trade_fields(metal, inputs, replacement_field_maps)
        optimized_inputs_by_year[year] = optimized_inputs
        transformed_cases.append(
            {
                "metal": metal,
                "year": year,
                "transformed_stage_triplets": applied_transition_slugs,
                "replaced_input_fields": sorted(replacement_field_maps),
            }
        )

    return optimized_inputs_by_year, transformed_cases


def export_first_optimization_cases(
    *,
    website_root: str | Path | None = None,
    conversion_factor_optimization_root: str | Path | None = None,
    raw_import_root: str | Path | None = None,
) -> dict[str, Any]:
    project_root = _resolve_project_root(website_root)
    default_cfo_root = get_project_paths().conversion_factor_optimization_root
    resolved_cfo_root = (
        Path(conversion_factor_optimization_root).resolve()
        if conversion_factor_optimization_root is not None
        else default_cfo_root.resolve()
    )
    resolved_raw_import_root = (
        Path(raw_import_root).resolve()
        if raw_import_root is not None
        else (
            (project_root / "data" / "shared" / "trade" / "raw_import_by_partner")
            if (project_root / "data" / "shared" / "trade" / "raw_import_by_partner").exists()
            else project_root / "data"
        )
    )
    first_optimization_root = project_root / "data" / "first_optimization"
    optimized_output_root = first_optimization_root / "optimized"
    comparison_root = first_optimization_root / "comparison"
    diagnostics_root = first_optimization_root / "diagnostics"
    diagnostics_output_root = diagnostics_root / "output"
    optimized_output_root.mkdir(parents=True, exist_ok=True)
    comparison_root.mkdir(parents=True, exist_ok=True)
    diagnostics_output_root.mkdir(parents=True, exist_ok=True)

    summary_frames: list[pd.DataFrame] = []
    stage_frames: list[pd.DataFrame] = []
    transformed_cases: list[dict[str, Any]] = []
    optimization_output_root = resolved_cfo_root / "output"
    if optimization_output_root.exists():
        shutil.copytree(optimization_output_root, diagnostics_output_root, dirs_exist_ok=True)
    batch_summary_path = resolved_cfo_root / "batch_run_summary.csv"
    if batch_summary_path.exists():
        shutil.copy2(batch_summary_path, diagnostics_root / "batch_run_summary.csv")

    for metal in pipeline_v1.METALS:
        optimized_inputs_by_year, metal_cases = build_optimized_inputs_by_year(
            metal=metal,
            conversion_factor_optimization_root=resolved_cfo_root,
            raw_import_root=resolved_raw_import_root,
        )
        transformed_cases.extend(metal_cases)
        for year in pipeline_v1.YEARS:
            optimized_inputs = optimized_inputs_by_year[year]
            nodes, links = pipeline_v1.build_country_graph(
                metal,
                year,
                inputs=optimized_inputs,
                cobalt_mode=pipeline_v1.DEFAULT_COBALT_MODE,
            )
            payload = {
                "metal": metal,
                "year": year,
                "optimization_source": "conversion_factor_optimization",
                "optimization_version": "first_optimization",
                "transformed_stage_triplets": next(
                    (row["transformed_stage_triplets"] for row in metal_cases if row["year"] == year),
                    [],
                ),
            }
            node_df, _link_df, summary_df = pipeline_v1._write_case_exports(
                optimized_output_root,
                metal,
                year,
                "optimized",
                optimized_inputs,
                nodes,
                links,
                payload,
            )
            summary_frames.append(summary_df)
            stage_frames.append(pipeline_v1.stage_summary(node_df))

    optimized_summary = pd.concat(summary_frames, ignore_index=True)
    optimized_stage = pd.concat(stage_frames, ignore_index=True)
    optimized_summary.to_csv(comparison_root / "optimized_summary.csv", index=False)
    optimized_stage.to_csv(comparison_root / "optimized_stage_summary.csv", index=False)

    baseline_summary_path = project_root / "data" / "original" / "comparison" / "baseline_summary.csv"
    comparison_rows = 0
    if baseline_summary_path.exists():
        baseline_summary = pd.read_csv(baseline_summary_path)
        comparison = baseline_summary.merge(
            optimized_summary,
            on=["metal", "year"],
            suffixes=("_baseline", "_optimized"),
        )
        comparison["unknown_reduction"] = comparison["unknown_total_baseline"] - comparison["unknown_total_optimized"]
        comparison["unknown_reduction_pct"] = comparison["unknown_reduction"] / comparison["unknown_total_baseline"].replace(0, pd.NA)
        comparison["special_reduction"] = comparison["total_special_baseline"] - comparison["total_special_optimized"]
        comparison.to_csv(comparison_root / "comparison_summary.csv", index=False)
        comparison_rows = int(len(comparison))

    return {
        "project_root": str(project_root),
        "conversion_factor_optimization_root": str(resolved_cfo_root),
        "raw_import_root": str(resolved_raw_import_root),
        "first_optimization_root": str(first_optimization_root),
        "diagnostics_root": str(diagnostics_root),
        "optimized_case_count": int(len(optimized_summary)),
        "comparison_row_count": comparison_rows,
        "transformed_cases": transformed_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert conversion_factor_optimization outputs into the web product's First Optimization case format."
    )
    parser.add_argument("--website-root", default=None, help="Project root for the consolidated monorepo.")
    parser.add_argument(
        "--conversion-factor-optimization-root",
        default=None,
        help="Explicit conversion_factor_optimization workspace root.",
    )
    parser.add_argument("--raw-import-root", default=None, help="Explicit raw UN Comtrade import root.")
    args = parser.parse_args(argv)
    result = export_first_optimization_cases(
        website_root=args.website_root,
        conversion_factor_optimization_root=args.conversion_factor_optimization_root,
        raw_import_root=args.raw_import_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
