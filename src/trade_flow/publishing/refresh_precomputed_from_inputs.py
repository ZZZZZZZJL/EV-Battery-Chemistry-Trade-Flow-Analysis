from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from battery_7step_site.services.cobalt_data import CobaltYearInputs
from battery_7step_site.services.lithium_data import LithiumYearInputs
from trade_flow.baseline import pipeline_v1


def _project_root(explicit_root: str | Path | None = None) -> Path:
    if explicit_root is not None:
        return Path(explicit_root).resolve()
    return Path(__file__).resolve().parents[3]


def _map_int_float(raw: dict[str, Any]) -> dict[int, float]:
    return {
        int(key): float(value)
        for key, value in (raw or {}).items()
    }


def _trade_rows(flow_type: type, rows: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        flow_type(
            exporter=int(item["exporter"]),
            importer=int(item["importer"]),
            value=float(item["value"]),
        )
        for item in rows
    )


def _load_lithium_inputs(inputs_json_path: Path) -> LithiumYearInputs:
    raw = json.loads(inputs_json_path.read_text(encoding="utf-8"))
    flow_type = pipeline_v1._bundle("Li")["data"].TradeFlow
    return LithiumYearInputs(
        mining_total=_map_int_float(raw["mining_total"]),
        mining_brine=_map_int_float(raw["mining_brine"]),
        mining_lithium_ores=_map_int_float(raw["mining_lithium_ores"]),
        processing_total=_map_int_float(raw["processing_total"]),
        processing_battery=_map_int_float(raw["processing_battery"]),
        processing_unrelated=_map_int_float(raw["processing_unrelated"]),
        processing_brine_total=_map_int_float(raw["processing_brine_total"]),
        processing_lithium_ores_total=_map_int_float(raw["processing_lithium_ores_total"]),
        processing_brine_balance=_map_int_float(raw["processing_brine_balance"]),
        processing_lithium_ores_balance=_map_int_float(raw["processing_lithium_ores_balance"]),
        refining_total=_map_int_float(raw["refining_total"]),
        refining_hydroxide=_map_int_float(raw["refining_hydroxide"]),
        refining_carbonate=_map_int_float(raw["refining_carbonate"]),
        refining_hydroxide_balance=_map_int_float(raw["refining_hydroxide_balance"]),
        refining_carbonate_balance=_map_int_float(raw["refining_carbonate_balance"]),
        cathode_total=_map_int_float(raw["cathode_total"]),
        cathode_ncm=_map_int_float(raw["cathode_ncm"]),
        cathode_nca=_map_int_float(raw["cathode_nca"]),
        cathode_lfp=_map_int_float(raw["cathode_lfp"]),
        cathode_ncm_nca_balance=_map_int_float(raw["cathode_ncm_nca_balance"]),
        cathode_ncm_balance=_map_int_float(raw["cathode_ncm_balance"]),
        cathode_nca_balance=_map_int_float(raw["cathode_nca_balance"]),
        cathode_lfp_balance=_map_int_float(raw["cathode_lfp_balance"]),
        trade1=_trade_rows(flow_type, raw["trade1"]),
        trade2=_trade_rows(flow_type, raw["trade2"]),
        trade3_hydroxide=_trade_rows(flow_type, raw["trade3_hydroxide"]),
        trade3_carbonate=_trade_rows(flow_type, raw["trade3_carbonate"]),
    )


def _load_cobalt_inputs(inputs_json_path: Path) -> CobaltYearInputs:
    raw = json.loads(inputs_json_path.read_text(encoding="utf-8"))
    flow_type = pipeline_v1._bundle("Co")["data"].TradeFlow
    return CobaltYearInputs(
        mining_total=_map_int_float(raw["mining_total"]),
        mining_battery=_map_int_float(raw["mining_battery"]),
        mining_concentrate=_map_int_float(raw["mining_concentrate"]),
        mining_sulphate=_map_int_float(raw["mining_sulphate"]),
        processing_total=_map_int_float(raw["processing_total"]),
        processing_unrelated=_map_int_float(raw["processing_unrelated"]),
        refining_max=_map_int_float(raw["refining_max"]),
        refining_mid=_map_int_float(raw["refining_mid"]),
        refining_min=_map_int_float(raw["refining_min"]),
        refining_max_balance=_map_int_float(raw["refining_max_balance"]),
        refining_mid_balance=_map_int_float(raw["refining_mid_balance"]),
        refining_min_balance=_map_int_float(raw["refining_min_balance"]),
        cathode_total=_map_int_float(raw["cathode_total"]),
        cathode_ncm=_map_int_float(raw["cathode_ncm"]),
        cathode_nca=_map_int_float(raw["cathode_nca"]),
        cathode_max_total_balance=_map_int_float(raw["cathode_max_total_balance"]),
        cathode_mid_total_balance=_map_int_float(raw["cathode_mid_total_balance"]),
        cathode_min_total_balance=_map_int_float(raw["cathode_min_total_balance"]),
        cathode_max_ncm_balance=_map_int_float(raw["cathode_max_ncm_balance"]),
        cathode_mid_ncm_balance=_map_int_float(raw["cathode_mid_ncm_balance"]),
        cathode_min_ncm_balance=_map_int_float(raw["cathode_min_ncm_balance"]),
        cathode_max_nca_balance=_map_int_float(raw["cathode_max_nca_balance"]),
        cathode_mid_nca_balance=_map_int_float(raw["cathode_mid_nca_balance"]),
        cathode_min_nca_balance=_map_int_float(raw["cathode_min_nca_balance"]),
        trade1=_trade_rows(flow_type, raw["trade1"]),
        trade2=_trade_rows(flow_type, raw["trade2"]),
        trade3=_trade_rows(flow_type, raw["trade3"]),
    )


def load_case_inputs_from_json(metal: str, inputs_json_path: str | Path) -> Any:
    path = Path(inputs_json_path)
    if metal == "Li":
        return _load_lithium_inputs(path)
    if metal == "Co":
        return _load_cobalt_inputs(path)
    raise ValueError(f"Unsupported metal for snapshot rebuild: {metal}")


def build_case_graphs_from_inputs_json(
    *,
    metal: str,
    year: int,
    scenario: str,
    inputs_json_path: str | Path,
) -> dict[str, tuple[dict[str, Any], list[Any]]]:
    del scenario
    inputs = load_case_inputs_from_json(metal, inputs_json_path)
    if metal == "Co":
        graphs: dict[str, tuple[dict[str, Any], list[Any]]] = {}
        for cobalt_mode in ("mid", "max", "min"):
            graphs[cobalt_mode] = pipeline_v1.build_country_graph(
                metal,
                year,
                inputs=inputs,
                cobalt_mode=cobalt_mode,
            )
        graphs["default"] = graphs["mid"]
        return graphs
    return {
        "default": pipeline_v1.build_country_graph(metal, year, inputs=inputs),
    }


def _case_frames(
    *,
    metal: str,
    year: int,
    scenario: str,
    nodes: dict[str, Any],
    links: list[Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    node_df = pd.DataFrame(pipeline_v1.node_records(nodes, links, metal, year, scenario))
    link_df = pd.DataFrame(pipeline_v1.link_records(nodes, links, metal, year, scenario))
    summary_df = pipeline_v1.summarize_graph(nodes, links, metal, year, scenario)[1]
    return node_df, link_df, summary_df


def _write_case_mode(
    *,
    case_dir: Path,
    metal: str,
    year: int,
    scenario: str,
    mode_suffix: str,
    nodes: dict[str, Any],
    links: list[Any],
    write: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if write:
        return pipeline_v1._write_case_mode_csvs(case_dir, metal, year, scenario, mode_suffix, nodes, links)
    return _case_frames(metal=metal, year=year, scenario=scenario, nodes=nodes, links=links)


def _replace_rows(existing: pd.DataFrame, replacement: pd.DataFrame, key_columns: list[str]) -> pd.DataFrame:
    if existing.empty:
        return replacement.copy()
    if replacement.empty:
        return existing.copy()
    replacement_keys = replacement[key_columns].drop_duplicates()
    merged = existing.merge(replacement_keys, on=key_columns, how="left", indicator=True)
    kept = merged.loc[merged["_merge"] == "left_only", existing.columns]
    combined = pd.concat([kept, replacement], ignore_index=True)
    return combined.sort_values(key_columns).reset_index(drop=True)


def refresh_li_co_precomputed_from_inputs(
    *,
    project_root: str | Path | None = None,
    write: bool = False,
) -> dict[str, Any]:
    root = _project_root(project_root)
    rebuilt_default_summaries: list[pd.DataFrame] = []
    rebuilt_default_stage_rows: list[pd.DataFrame] = []
    report_cases: list[dict[str, Any]] = []

    li_cases = [
        ("baseline", root / "data" / "original" / "baseline" / "Li", "baseline"),
        ("optimized", root / "data" / "first_optimization" / "optimized" / "Li", "optimized"),
    ]
    for scenario_name, case_root, scenario in li_cases:
        for year in pipeline_v1.YEARS:
            case_dir = case_root / str(year)
            graphs = build_case_graphs_from_inputs_json(
                metal="Li",
                year=year,
                scenario=scenario,
                inputs_json_path=case_dir / f"{scenario}_inputs.json",
            )
            nodes, links = graphs["default"]
            node_df, _link_df, summary_df = _write_case_mode(
                case_dir=case_dir,
                metal="Li",
                year=year,
                scenario=scenario,
                mode_suffix="",
                nodes=nodes,
                links=links,
                write=write,
            )
            rebuilt_default_summaries.append(summary_df)
            rebuilt_default_stage_rows.append(pipeline_v1.stage_summary(node_df))
            report_cases.append(
                {
                    "metal": "Li",
                    "year": year,
                    "scenario": scenario_name,
                    "case_dir": str(case_dir),
                }
            )

    co_root = root / "data" / "first_optimization" / "optimized" / "Co"
    for year in pipeline_v1.YEARS:
        case_dir = co_root / str(year)
        graphs = build_case_graphs_from_inputs_json(
            metal="Co",
            year=year,
            scenario="optimized",
            inputs_json_path=case_dir / "optimized_inputs.json",
        )
        default_nodes, default_links = graphs["default"]
        node_df, _link_df, summary_df = _write_case_mode(
            case_dir=case_dir,
            metal="Co",
            year=year,
            scenario="optimized",
            mode_suffix="",
            nodes=default_nodes,
            links=default_links,
            write=write,
        )
        rebuilt_default_summaries.append(summary_df)
        rebuilt_default_stage_rows.append(pipeline_v1.stage_summary(node_df))
        for cobalt_mode in ("mid", "max", "min"):
            mode_nodes, mode_links = graphs[cobalt_mode]
            _write_case_mode(
                case_dir=case_dir,
                metal="Co",
                year=year,
                scenario="optimized",
                mode_suffix=cobalt_mode,
                nodes=mode_nodes,
                links=mode_links,
                write=write,
            )
        report_cases.append(
            {
                "metal": "Co",
                "year": year,
                "scenario": "first_optimization",
                "case_dir": str(case_dir),
            }
        )

    rebuilt_summary = pd.concat(rebuilt_default_summaries, ignore_index=True)
    rebuilt_stage = pd.concat(rebuilt_default_stage_rows, ignore_index=True)

    original_comparison_root = root / "data" / "original" / "comparison"
    original_summary_path = original_comparison_root / "baseline_summary.csv"
    original_stage_path = original_comparison_root / "baseline_stage_summary.csv"
    original_summary = pd.read_csv(original_summary_path)
    original_stage = pd.read_csv(original_stage_path)
    new_li_baseline_summary = rebuilt_summary.loc[
        (rebuilt_summary["metal"] == "Li") & rebuilt_summary["scenario"].eq("baseline")
    ].copy()
    new_li_baseline_stage = rebuilt_stage.loc[
        (rebuilt_stage["metal"] == "Li") & rebuilt_stage["scenario"].eq("baseline")
    ].copy()
    updated_original_summary = _replace_rows(original_summary, new_li_baseline_summary, ["metal", "year", "scenario"])
    updated_original_stage = _replace_rows(original_stage, new_li_baseline_stage, ["metal", "year", "scenario", "stage"])

    optimized_comparison_root = root / "data" / "first_optimization" / "comparison"
    optimized_summary_path = optimized_comparison_root / "optimized_summary.csv"
    optimized_stage_path = optimized_comparison_root / "optimized_stage_summary.csv"
    optimized_summary = pd.read_csv(optimized_summary_path)
    optimized_stage = pd.read_csv(optimized_stage_path)
    new_optimized_summary = rebuilt_summary.loc[
        (rebuilt_summary["scenario"] == "optimized") & rebuilt_summary["metal"].isin(["Li", "Co"])
    ].copy()
    new_optimized_stage = rebuilt_stage.loc[
        (rebuilt_stage["scenario"] == "optimized") & rebuilt_stage["metal"].isin(["Li", "Co"])
    ].copy()
    updated_optimized_summary = _replace_rows(optimized_summary, new_optimized_summary, ["metal", "year", "scenario"])
    updated_optimized_stage = _replace_rows(optimized_stage, new_optimized_stage, ["metal", "year", "scenario", "stage"])

    comparison = updated_original_summary.merge(
        updated_optimized_summary,
        on=["metal", "year"],
        suffixes=("_baseline", "_optimized"),
    )
    comparison["unknown_reduction"] = comparison["unknown_total_baseline"] - comparison["unknown_total_optimized"]
    comparison["unknown_reduction_pct"] = comparison["unknown_reduction"] / comparison["unknown_total_baseline"].replace(0, pd.NA)
    comparison["special_reduction"] = comparison["total_special_baseline"] - comparison["total_special_optimized"]

    if write:
        updated_original_summary.to_csv(original_summary_path, index=False)
        updated_original_stage.to_csv(original_stage_path, index=False)
        updated_optimized_summary.to_csv(optimized_summary_path, index=False)
        updated_optimized_stage.to_csv(optimized_stage_path, index=False)
        comparison.to_csv(optimized_comparison_root / "comparison_summary.csv", index=False)

    return {
        "project_root": str(root),
        "write": write,
        "case_count": len(report_cases),
        "cases": report_cases,
        "baseline_rows": int(len(new_li_baseline_summary)),
        "optimized_rows": int(len(new_optimized_summary)),
    }


__all__ = [
    "build_case_graphs_from_inputs_json",
    "load_case_inputs_from_json",
    "refresh_li_co_precomputed_from_inputs",
]
