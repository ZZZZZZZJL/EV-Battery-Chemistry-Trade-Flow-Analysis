from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from trade_flow.legacy_site.config import get_battery_site_config
from trade_flow.legacy_site.services.datasets import load_dataset_config
from trade_flow.legacy_site.services.first_optimization_tables import FirstOptimizationTableSource
from trade_flow.legacy_site.services.reference import load_reference_frame


SCENARIOS = ("baseline", "first_optimization")
SCENARIO_LABELS = {
    "baseline": "Original",
    "first_optimization": "First Optimization",
}
TABLE_VIEWS = ("auto", "baseline", "optimized", "compare")
TABLE_VIEW_LABELS = {
    "auto": "Follow Result",
    "baseline": "Original Only",
    "optimized": "Optimized Only",
    "compare": "Compare",
}
CASE_FILE_MAP = {
    "baseline": {
        "nodes": "baseline_nodes.csv",
        "links": "baseline_links.csv",
        "summary": "baseline_summary.csv",
        "payload": "baseline_payload.json",
        "inputs": "baseline_inputs.json",
    },
    "optimized": {
        "nodes": "optimized_nodes.csv",
        "links": "optimized_links.csv",
        "summary": "optimized_summary.csv",
        "payload": "optimized_payload.json",
        "inputs": "optimized_inputs.json",
    },
}
SCENARIO_CASE_KIND = {
    "baseline": "baseline",
    "first_optimization": "optimized",
}
METRIC_ORDER = [
    ("unknown_total", "Unknown Total"),
    ("non_source_total", "From Non-Source Countries"),
    ("non_target_total", "To Non-Target Countries"),
    ("structural_sink_total", "Structural Sink"),
    ("total_special", "Total Special"),
    ("total_regular", "Total Regular"),
]
PARAMETER_LABELS = {
    "mirror_weight": "Mirror Weight",
    "lag_weight": "Lag Weight",
    "hub_threshold": "Hub Threshold",
    "reexport_cap": "Re-export Cap",
    "priority_country_count": "Priority Country Count",
    "scale_lower": "Exporter Scale Lower",
    "scale_upper": "Exporter Scale Upper",
    "scale_step": "Exporter Scale Step",
    "scale_passes": "Scale Passes",
    "deviation_weight": "Deviation Weight",
    "non_source_weight": "Non-Source Weight",
    "non_target_weight": "Non-Target Weight",
    "source_priority_count": "Source Priority Count",
    "dual_priority_count": "Dual-role Priority Count",
    "source_alpha_lower": "Source Alpha Lower",
    "source_alpha_upper": "Source Alpha Upper",
    "dual_alpha_lower": "Dual-role Alpha Lower",
    "dual_alpha_upper": "Dual-role Alpha Upper",
    "alpha_step": "Alpha Step",
    "max_residual_weight": "Max Residual Weight",
    "pp_penalty": "PP Deviation Penalty",
    "pn_up_penalty": "PN Upward Penalty",
    "pn_down_penalty": "PN Downward Penalty",
    "np_up_penalty": "NP Upward Penalty",
    "np_down_penalty": "NP Downward Penalty",
    "pp_smooth_penalty": "PP Smoothness Penalty",
    "pn_smooth_penalty": "PN Smoothness Penalty",
    "np_smooth_penalty": "NP Smoothness Penalty",
    "coefficient_step": "Coefficient Step",
    "coordinate_passes": "Coordinate Passes",
    "unknown_source_weight": "Unknown Source Weight",
    "unknown_destination_weight": "Unknown Destination Weight",
    "shared_pp_priority": "Shared PP Priority",
    "shared_pn_priority": "Shared PN Priority",
}
TRANSITION_LABELS = {
    "trade1": "Trade 1 / S1-S3",
    "trade2": "Trade 2 / S3-S5",
    "trade3": "Trade 3 / S5-S7",
}
PRODUCER_TRANSITION_LABELS = {
    "trade1": "S1-S3: 1st Post Trade",
    "trade2": "S3-S5: 2nd Post Trade",
    "trade3": "S5-S7: 3rd Post Trade",
}
COBALT_MODES = ("mid", "max", "min")


def _ordered_param_items(params: dict[str, Any]) -> list[tuple[str, Any]]:
    preferred = [key for key in PARAMETER_LABELS if key in params]
    remaining = [key for key in params if key not in preferred]
    ordered_keys = preferred + sorted(remaining)
    return [(key, params[key]) for key in ordered_keys]


def _folder_has_real_hs_code(folder_name: str) -> bool:
    tail = str(folder_name or "").rsplit("/", 1)[-1]
    if "_" not in tail:
        return True
    hs_code = tail.rsplit("_", 1)[-1]
    return not hs_code.isdigit() or any(char != "0" for char in hs_code)



def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _json_dict(raw: Any) -> dict[str, Any]:
    if raw in (None, "", {}):
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_list(raw: Any) -> list[Any]:
    if raw in (None, "", []):
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _compact_identifier_list(values: list[Any], limit: int = 8) -> str:
    cleaned = [str(value) for value in values if str(value)]
    if not cleaned:
        return "-"
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    visible = ", ".join(cleaned[:limit])
    return f"{visible}, +{len(cleaned) - limit} more"


def _format_coefficient_label(raw: Any) -> str:
    text = str(raw or "")
    if "|" in text:
        text = text.split("|", 1)[1]
    text = text.replace("non_source", "Non-source pool")
    text = text.replace("non_target", "Non-target countries")
    return text.replace("->", " -> ").strip()



def _format_country_code(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "-"
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return str(int(numeric))
    return text


def _format_country_name(raw: Any, name_map: dict[int, str]) -> str:
    code = _format_country_code(raw)
    if code == "-":
        return code
    try:
        numeric = int(code)
    except ValueError:
        return code
    return name_map.get(numeric, code)


def _format_hs_display(folder_name: str) -> str:
    tail = str(folder_name or "").rsplit("/", 1)[-1]
    if "_" not in tail:
        return tail
    suffix = tail.rsplit("_", 1)[-1]
    return suffix if suffix else tail


def _mode_suffix(metal: str, cobalt_mode: str) -> str:
    if metal != "Co":
        return ""
    normalized = str(cobalt_mode or "mid").lower()
    return f"_{normalized}" if normalized in COBALT_MODES else ""


def _case_file_candidates(case_dir: Path, base_filename: str, metal: str, cobalt_mode: str) -> list[Path]:
    suffix = _mode_suffix(metal, cobalt_mode)
    if suffix:
        stem = Path(base_filename).stem
        extension = Path(base_filename).suffix
        candidate = case_dir / f"{stem}{suffix}{extension}"
        return [candidate, case_dir / base_filename]
    return [case_dir / base_filename]


def _transition_file_candidates(comparison_dir: Path, base_filename: str, metal: str, cobalt_mode: str) -> list[Path]:
    suffix = _mode_suffix(metal, cobalt_mode)
    if suffix:
        stem = Path(base_filename).stem
        extension = Path(base_filename).suffix
        return [comparison_dir / f"{stem}{suffix}{extension}", comparison_dir / base_filename]
    return [comparison_dir / base_filename]


def _intermediate_file_candidates(intermediate_dir: Path, base_filename: str, metal: str, cobalt_mode: str) -> list[Path]:
    suffix = _mode_suffix(metal, cobalt_mode)
    if suffix:
        stem = Path(base_filename).stem
        extension = Path(base_filename).suffix
        return [intermediate_dir / f"{stem}{suffix}{extension}", intermediate_dir / base_filename]
    return [intermediate_dir / base_filename]


def _first_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _special_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    return (
        frame.get("kind", "regular").astype(str).ne("regular")
        | frame.get("is_unknown", 0).astype(int).eq(1)
        | frame.get("is_non_source", 0).astype(int).eq(1)
        | frame.get("is_non_target", 0).astype(int).eq(1)
        | frame.get("is_structural_sink", 0).astype(int).eq(1)
    )


def _stage_rows_from_nodes(nodes: pd.DataFrame) -> list[dict[str, Any]]:
    if nodes.empty:
        return []
    working = nodes.copy()
    working["value"] = pd.to_numeric(working["value"], errors="coerce").fillna(0.0)
    special_mask = _special_mask(working)
    rows: list[dict[str, Any]] = []
    for stage, group in working.groupby("stage", sort=True):
        special_group = group.loc[special_mask.loc[group.index]]
        rows.append(
            {
                "stage": stage,
                "total_value": float(group["value"].sum()),
                "unknown_total": float(group.loc[group["is_unknown"].astype(int).eq(1), "value"].sum()),
                "special_total": float(special_group["value"].sum()),
            }
        )
    return rows


def _comparison_from_rows(baseline: dict[str, Any], optimized: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {"metal": baseline.get("metal"), "year": baseline.get("year")}
    for key, _label in METRIC_ORDER:
        baseline_value = _safe_float(baseline.get(key))
        optimized_value = _safe_float(optimized.get(key))
        merged[f"{key}_baseline"] = baseline_value
        merged[f"{key}_optimized"] = optimized_value
    merged["unknown_reduction"] = merged["unknown_total_baseline"] - merged["unknown_total_optimized"]
    baseline_unknown = merged["unknown_total_baseline"]
    merged["unknown_reduction_pct"] = (merged["unknown_reduction"] / baseline_unknown) if abs(baseline_unknown) > 1e-9 else 0.0
    merged["special_reduction"] = merged["total_special_baseline"] - merged["total_special_optimized"]
    return merged


@dataclass
class OutputRepository:
    """Read-only access layer for precomputed baseline / optimized outputs."""

    original_data_root: Path
    first_optimization_data_root: Path
    first_optimization_diagnostics_root: Path
    version_output_root: Path

    def __post_init__(self) -> None:
        self._case_csv_cache: dict[tuple[str, int, str, str, str], pd.DataFrame] = {}
        self._case_json_cache: dict[tuple[str, int, str, str, str], Any] = {}
        self._transition_frame_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._coefficient_frame_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self.scenario_output_dirs = {
            "baseline": self.original_data_root,
            "first_optimization": self.first_optimization_data_root,
        }
        self.scenario_comparison_dirs = {
            "baseline": self.original_data_root / "comparison",
            "first_optimization": self.first_optimization_data_root / "comparison",
        }
        self.comparison_dir = self.scenario_comparison_dirs["first_optimization"]
        self.summary_frames = {
            scenario: pd.read_csv(
                self.scenario_comparison_dirs[scenario]
                / ("baseline_summary.csv" if SCENARIO_CASE_KIND[scenario] == "baseline" else "optimized_summary.csv")
            )
            for scenario in SCENARIOS
        }
        self.stage_frames = {
            scenario: pd.read_csv(
                self.scenario_comparison_dirs[scenario]
                / ("baseline_stage_summary.csv" if SCENARIO_CASE_KIND[scenario] == "baseline" else "optimized_stage_summary.csv")
            )
            for scenario in SCENARIOS
        }
        self.comparison_frames = {
            "first_optimization": pd.read_csv(self.scenario_comparison_dirs["first_optimization"] / "comparison_summary.csv"),
        }
        transition_detail_path = self.scenario_comparison_dirs["first_optimization"] / "optimized_transition_detail.csv"
        self.transition_frames = {
            "first_optimization": pd.read_csv(transition_detail_path).fillna("") if transition_detail_path.exists() else pd.DataFrame(),
        }
        self.feasibility_by_scenario = {}
        for scenario in ("first_optimization",):
            feasibility_path = self.scenario_comparison_dirs[scenario] / "feasibility_summary.json"
            if feasibility_path.exists():
                with feasibility_path.open("r", encoding="utf-8") as handle:
                    self.feasibility_by_scenario[scenario] = json.load(handle)
            else:
                self.feasibility_by_scenario[scenario] = {"best_params_by_metal": {}}
        self.cobalt_mode_results: dict[str, dict[str, Any]] = {}
        for scenario in ("first_optimization",):
            results_path = self.scenario_comparison_dirs[scenario] / "cobalt_mode_results.json"
            if results_path.exists():
                with results_path.open("r", encoding="utf-8") as handle:
                    self.cobalt_mode_results[scenario] = json.load(handle)
            else:
                self.cobalt_mode_results[scenario] = {}
        self.country_name_by_id: dict[int, str] = {}
        try:
            reference_file = load_dataset_config().get("referenceFile", "")
            if reference_file:
                reference_frame = load_reference_frame(reference_file)
                self.country_name_by_id = {
                    int(row.id): str(row.name).strip()
                    for row in reference_frame[["id", "name"]].itertuples(index=False)
                    if pd.notna(row.id) and str(row.name).strip()
                }
        except Exception:
            self.country_name_by_id = {}
        self.first_optimization_tables = FirstOptimizationTableSource(
            self.first_optimization_diagnostics_root,
            self.country_name_by_id,
        )

        preferred_order = ["Ni", "Li", "Co"]
        available = {str(value) for value in self.summary_frames["baseline"]["metal"].unique().tolist()}
        self.metals = [metal for metal in preferred_order if metal in available]
        self.years = sorted(int(value) for value in self.summary_frames["baseline"]["year"].unique().tolist())

    def _resolve_output_dir(self, version_key: str) -> Path:
        candidate = self.version_output_root / version_key / "output"
        return candidate if candidate.exists() else self.first_optimization_data_root

    def case_dir(self, metal: str, year: int, scenario: str) -> Path:
        case_kind = SCENARIO_CASE_KIND[scenario]
        return self.scenario_output_dirs[scenario] / case_kind / metal / str(year)

    def load_case_csv(self, metal: str, year: int, scenario: str, kind: str, cobalt_mode: str = "mid") -> pd.DataFrame:
        cache_key = (metal, year, scenario, kind, cobalt_mode)
        if cache_key in self._case_csv_cache:
            return self._case_csv_cache[cache_key]
        filename = CASE_FILE_MAP[SCENARIO_CASE_KIND[scenario]][kind]
        case_dir = self.case_dir(metal, year, scenario)
        path = _first_existing_path(_case_file_candidates(case_dir, filename, metal, cobalt_mode))
        frame = pd.read_csv(path)
        self._case_csv_cache[cache_key] = frame
        return frame

    def load_case_json(self, metal: str, year: int, scenario: str, kind: str, cobalt_mode: str = "mid") -> Any:
        cache_key = (metal, year, scenario, kind, cobalt_mode)
        if cache_key in self._case_json_cache:
            return self._case_json_cache[cache_key]
        filename = CASE_FILE_MAP[SCENARIO_CASE_KIND[scenario]][kind]
        case_dir = self.case_dir(metal, year, scenario)
        path = _first_existing_path(_case_file_candidates(case_dir, filename, metal, cobalt_mode))
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self._case_json_cache[cache_key] = payload
        return payload

    def get_summary_row(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> dict[str, Any]:
        frame = self.load_case_csv(metal, year, scenario, "summary", cobalt_mode)
        row = frame[(frame["metal"] == metal) & (frame["year"] == year)] if "metal" in frame and "year" in frame else frame
        if row.empty:
            raise KeyError(f"Missing summary row for {metal} {year} {scenario}")
        return row.iloc[0].to_dict()

    def get_stage_rows(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        nodes = self.load_case_csv(metal, year, scenario, "nodes", cobalt_mode)
        return _stage_rows_from_nodes(nodes)

    def get_comparison_row(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> dict[str, Any]:
        if scenario == "first_optimization" and self.first_optimization_tables.available:
            return self.first_optimization_tables.comparison_row(metal, year)
        baseline = self.get_summary_row(metal, year, "baseline", cobalt_mode)
        optimized = self.get_summary_row(metal, year, scenario, cobalt_mode)
        return _comparison_from_rows(baseline, optimized)

    def _load_transition_frame(self, scenario: str, metal: str, cobalt_mode: str) -> pd.DataFrame:
        cache_key = (scenario, cobalt_mode)
        if cache_key in self._transition_frame_cache:
            return self._transition_frame_cache[cache_key]
        path = _first_existing_path(
            _transition_file_candidates(self.scenario_comparison_dirs[scenario], "optimized_transition_detail.csv", metal, cobalt_mode)
        )
        frame = pd.read_csv(path).fillna("") if path.exists() else pd.DataFrame()
        self._transition_frame_cache[cache_key] = frame
        return frame

    def _load_coefficient_frame(self, scenario: str, metal: str, cobalt_mode: str) -> pd.DataFrame:
        cache_key = (scenario, cobalt_mode)
        if cache_key in self._coefficient_frame_cache:
            return self._coefficient_frame_cache[cache_key]
        intermediate_dir = self.scenario_output_dirs[scenario] / "intermediate"
        preferred_candidates = _intermediate_file_candidates(
            intermediate_dir,
            "first_optimization_coefficients.csv",
            metal,
            cobalt_mode,
        )
        path = next((candidate for candidate in preferred_candidates if candidate.exists()), None)
        if path is None:
            wildcard_candidates = sorted(intermediate_dir.glob("*coefficients*.csv"))
            path = wildcard_candidates[0] if wildcard_candidates else preferred_candidates[0]
        frame = pd.read_csv(path).fillna("") if path.exists() else pd.DataFrame()
        self._coefficient_frame_cache[cache_key] = frame
        return frame

    def get_transition_rows(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if scenario == "first_optimization" and self.first_optimization_tables.available:
            return self.first_optimization_tables.transition_rows(metal, year)
        if scenario != "first_optimization":
            return []
        frame = self._load_transition_frame(scenario, metal, cobalt_mode)
        rows = frame[(frame["metal"] == metal) & (frame["year"] == year)].copy()
        if rows.empty:
            return []
        decoded: list[dict[str, Any]] = []
        for record in rows.to_dict(orient="records"):
            folder_name = str(record.get("folder_name", ""))
            if not _folder_has_real_hs_code(folder_name):
                continue

            params = _json_dict(record.get("params_json"))
            multipliers = _json_dict(record.get("multipliers_json"))
            coefficient_summary = _json_dict(record.get("coefficient_summary_json"))
            folder_parts = folder_name.split("/", 1)
            folder_group = folder_parts[0] if folder_parts else folder_name
            folder_display = folder_parts[-1] if folder_parts else folder_name
            stage_unknown = _safe_float(record.get("stage_unknown_total"))
            non_source = _safe_float(record.get("non_source_total"))
            non_target = _safe_float(record.get("non_target_total"))
            raw_total = _safe_float(record.get("folder_raw_total"))
            optimized_total = _safe_float(record.get("folder_optimized_total"))
            flow_delta = optimized_total - raw_total
            parameter_pairs = [
                {"label": PARAMETER_LABELS.get(key, key), "value": value}
                for key, value in _ordered_param_items(params)
            ]
            diagnostic_version = "first_optimization" if scenario == "first_optimization" else "baseline"
            is_advanced = scenario == "first_optimization" or bool(coefficient_summary)
            signal_source = coefficient_summary if is_advanced and coefficient_summary else multipliers
            has_signal = bool(signal_source) or stage_unknown > 0.0 or non_source > 0.0 or non_target > 0.0 or abs(flow_delta) > 1e-9

            diagnostic_pills = [
                {"label": "Stage Unknown", "value": stage_unknown, "tone": "unknown"},
                {"label": "Non-Source", "value": non_source, "tone": "source"},
                {"label": "Non-Target", "value": non_target, "tone": "target"},
            ]
            multiplier_pairs = [
                {"label": str(key), "value": float(value)}
                for key, value in sorted(
                    signal_source.items(),
                    key=lambda item: (abs(float(item[1]) - 1.0), str(item[0])),
                    reverse=True,
                )
            ]
            if is_advanced:
                source_producers = _json_list(record.get("source_producers_json"))
                target_producers = _json_list(record.get("target_producers_json"))
                coefficient_pairs = [
                    {"label": _format_coefficient_label(key), "value": float(value)}
                    for key, value in sorted(
                        coefficient_summary.items(),
                        key=lambda item: (abs(float(item[1]) - 1.0), str(item[0])),
                        reverse=True,
                    )
                ]
                coefficient_count = _safe_int(record.get("coefficient_count"))
                bound_hit_count = _safe_int(record.get("bound_hit_count"))
                edge_mix_pairs = [
                    {"label": "PP edges", "value": _safe_int(record.get("pp_edge_count"))},
                    {"label": "PN edges", "value": _safe_int(record.get("pn_edge_count"))},
                    {"label": "NP edges", "value": _safe_int(record.get("np_edge_count"))},
                    {"label": "NN edges", "value": _safe_int(record.get("nn_edge_count"))},
                ]
                producer_pairs = [
                    {
                        "label": "Source producers",
                        "value": _safe_int(record.get("source_producer_count")),
                        "note": _compact_identifier_list(source_producers),
                    },
                    {
                        "label": "Target producers",
                        "value": _safe_int(record.get("target_producer_count")),
                        "note": _compact_identifier_list(target_producers),
                    },
                ]
                flow_pairs = [
                    {"label": "Raw flow", "value": raw_total},
                    {"label": "Optimized flow", "value": optimized_total},
                    {"label": "Flow delta", "value": flow_delta},
                    {"label": "Coefficient count", "value": coefficient_count},
                    {"label": "Bound hits", "value": bound_hit_count},
                ]
                diagnostic_pills.extend(
                    [
                        {"label": "Raw Flow", "value": raw_total, "tone": "neutral"},
                        {"label": "Optimized Flow", "value": optimized_total, "tone": "neutral"},
                        {
                            "label": "Bound Hits",
                            "value": f"{bound_hit_count}/{coefficient_count}" if coefficient_count else "0/0",
                            "tone": "neutral",
                        },
                    ]
                )
                diagnostic_panels = [
                    {
                        "title": "Coefficient Summary",
                        "subtitle": "Import-only PP / PN / NP coefficients active in this HS folder",
                        "items": coefficient_pairs,
                        "emptyText": "No coefficient adjustments were recorded for this HS folder.",
                    },
                    {
                        "title": "Producer Sets",
                        "subtitle": "Source and target producers inferred from the production workbook",
                        "items": producer_pairs,
                        "emptyText": "No producer-set metadata was recorded.",
                    },
                    {
                        "title": "Edge Mix",
                        "subtitle": "Existing import edges grouped by producer relationship",
                        "items": edge_mix_pairs,
                        "emptyText": "No edge-class summary was recorded.",
                    },
                    {
                        "title": "Flow And Bounds",
                        "subtitle": "Raw vs optimized volume and how often coefficients hit their limits",
                        "items": flow_pairs,
                        "emptyText": "No flow summary was recorded.",
                    },
                    {
                        "title": "Applied Hyperparameters",
                        "subtitle": "Shared optimization penalty, smoothness, and cap-priority settings",
                        "items": parameter_pairs,
                        "emptyText": "No hyperparameter signature was recorded.",
                    },
                ]
                optimize_enabled = str(record.get("optimize_enabled", "")).lower() == "true"
                skipped_reason = str(record.get("skipped_reason", "") or "").strip()
                signal_label = "Optimized" if optimize_enabled else "Baseline pass-through"
                if skipped_reason:
                    signal_label = "Skipped"
                signal_class = "positive" if optimize_enabled and has_signal else "neutral"
                card_note = folder_group if not skipped_reason else f"{folder_group} | {skipped_reason}"
                priority_multipliers = ", ".join(f"{key}: {value}" for key, value in coefficient_summary.items()) or "-"
            else:
                diagnostic_panels = [
                    {
                        "title": "Priority Multipliers",
                        "subtitle": "Country-level scale shifts",
                        "items": multiplier_pairs,
                        "emptyText": "No country-level multipliers were applied for this HS folder.",
                    },
                    {
                        "title": "Applied Hyperparameters",
                        "subtitle": "Shared metal-level setting set",
                        "items": parameter_pairs,
                        "emptyText": "No hyperparameter signature was recorded.",
                    },
                ]
                signal_label = "Tuned" if has_signal else "No visible adjustment"
                signal_class = "positive" if has_signal else "neutral"
                card_note = folder_group
                priority_multipliers = ", ".join(f"{key}: {value}" for key, value in signal_source.items()) or "-"

            decoded.append(
                {
                    **record,
                    "diagnostic_kind": diagnostic_version if is_advanced else "baseline",
                    "transition_display": TRANSITION_LABELS.get(str(record.get("transition", "")), str(record.get("transition", ""))),
                    "folder_group": folder_group,
                    "folder_display": folder_display,
                    "multiplier_pairs": multiplier_pairs,
                    "parameter_pairs": parameter_pairs,
                    "diagnostic_pills": diagnostic_pills,
                    "diagnostic_panels": diagnostic_panels,
                    "signal_label": signal_label,
                    "signal_class": signal_class,
                    "card_note": card_note,
                    "has_signal": has_signal,
                    "priority_multipliers": priority_multipliers,
                    "param_signature": ", ".join(f"{key}={value}" for key, value in params.items()) or "-",
                }
            )
        return decoded

    def get_best_params(self, metal: str, scenario: str, cobalt_mode: str = "mid") -> dict[str, Any]:
        if scenario not in self.feasibility_by_scenario:
            return {}
        if metal == "Co":
            mode_results = self.cobalt_mode_results.get(scenario, {})
            if cobalt_mode in mode_results:
                return mode_results[cobalt_mode]
        return self.feasibility_by_scenario[scenario]["best_params_by_metal"].get(metal, {})


    def get_producer_coefficient_rows(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if scenario == "baseline":
            return []
        if scenario == "first_optimization" and self.first_optimization_tables.available:
            return self.first_optimization_tables.producer_coefficient_rows(metal, year)
        frame = self._load_coefficient_frame(scenario, metal, cobalt_mode)
        if frame.empty:
            return []
        rows = frame[(frame["metal"] == metal) & (frame["year"].astype(str) == str(year))].copy()
        if rows.empty:
            return []

        decoded: list[dict[str, Any]] = []
        for record in rows.to_dict(orient="records"):
            folder_name = str(record.get("folder_name", ""))
            if not _folder_has_real_hs_code(folder_name):
                continue
            coefficient_class = str(record.get("coefficient_class", ""))
            exporter = _format_country_name(record.get("exporter"), self.country_name_by_id)
            importer = _format_country_name(record.get("importer"), self.country_name_by_id)
            if coefficient_class == "PP":
                producer_scope = f"Source {exporter} -> Target {importer}"
                partner_scope = importer
            elif coefficient_class == "PN":
                producer_scope = f"Source {exporter}"
                partner_scope = "All non-target producers"
            elif coefficient_class == "NP":
                producer_scope = f"Target {importer}"
                partner_scope = "All non-source exporters"
            else:
                producer_scope = exporter if exporter != "-" else importer
                partner_scope = importer if importer != "-" else "-"

            hit_lower = _safe_int(record.get("hit_lower"))
            hit_upper = _safe_int(record.get("hit_upper"))
            bound_status = "Interior"
            if hit_upper:
                bound_status = "Upper"
            elif hit_lower:
                bound_status = "Lower"

            decoded.append(
                {
                    "transition": str(record.get("transition", "")),
                    "transition_display": PRODUCER_TRANSITION_LABELS.get(str(record.get("transition", "")), str(record.get("transition", ""))),
                    "hs_code": _format_hs_display(folder_name),
                    "coefficient_class": coefficient_class,
                    "producer_scope": producer_scope,
                    "partner_scope": partner_scope,
                    "coef_value": _safe_float(record.get("coef_value")),
                    "bounds": f"[{_safe_float(record.get('lower_bound')):.2f}, {_safe_float(record.get('upper_bound')):.2f}]",
                    "bound_status": bound_status,
                    "exposure": _safe_float(record.get("exposure")),
                    "exposure_share": _safe_float(record.get("exposure_share")),
                }
            )
        transition_rank = {"trade1": 0, "trade2": 1, "trade3": 2}
        decoded.sort(
            key=lambda row: (
                transition_rank.get(row["transition"], len(transition_rank)),
                row["hs_code"],
                row["coefficient_class"],
                row["producer_scope"],
            )
        )
        return decoded

    def build_metric_rows(self, metal: str, year: int, scenario: str, table_view: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if scenario == "first_optimization" and self.first_optimization_tables.available:
            return self.first_optimization_tables.metric_rows(metal, year)
        if table_view == "compare" and scenario != "baseline":
            comparison = self.get_comparison_row(metal, year, scenario, cobalt_mode)
            rows: list[dict[str, Any]] = []
            for key, label in METRIC_ORDER:
                baseline_value = comparison[f"{key}_baseline"]
                optimized_value = comparison[f"{key}_optimized"]
                rows.append(
                    {
                        "metric": label,
                        "baseline": baseline_value,
                        "optimized": optimized_value,
                        "delta": optimized_value - baseline_value,
                    }
                )
            rows.append(
                {
                    "metric": "Unknown Reduction %",
                    "baseline": "",
                    "optimized": "",
                    "delta": comparison["unknown_reduction_pct"],
                }
            )
            return rows

        summary = self.get_summary_row(metal, year, scenario, cobalt_mode)
        return [{"metric": label, "value": summary[key]} for key, label in METRIC_ORDER]

    def build_stage_rows(self, metal: str, year: int, scenario: str, table_view: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if scenario == "first_optimization" and self.first_optimization_tables.available:
            return self.first_optimization_tables.stage_rows(metal, year)
        if table_view == "compare" and scenario != "baseline":
            baseline_rows = {row["stage"]: row for row in self.get_stage_rows(metal, year, "baseline", cobalt_mode)}
            optimized_rows = {row["stage"]: row for row in self.get_stage_rows(metal, year, scenario, cobalt_mode)}
            rows: list[dict[str, Any]] = []
            for stage in sorted(set(baseline_rows) | set(optimized_rows)):
                base = baseline_rows.get(stage, {})
                opt = optimized_rows.get(stage, {})
                rows.append(
                    {
                        "stage": stage,
                        "baseline_unknown": base.get("unknown_total", 0.0),
                        "optimized_unknown": opt.get("unknown_total", 0.0),
                        "unknown_delta": opt.get("unknown_total", 0.0) - base.get("unknown_total", 0.0),
                        "baseline_special": base.get("special_total", 0.0),
                        "optimized_special": opt.get("special_total", 0.0),
                    }
                )
            return rows

        return self.get_stage_rows(metal, year, scenario, cobalt_mode)

    def build_parameter_rows(
        self,
        metal: str,
        scenario: str,
        table_view: str,
        cobalt_mode: str = "mid",
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        if scenario == "first_optimization" and self.first_optimization_tables.available:
            return self.first_optimization_tables.parameter_rows(metal, year)
        if table_view == "compare" and scenario != "baseline":
            best = self.get_best_params(metal, scenario, cobalt_mode)
            params = best.get("best_params", {})
            rows = [
                {
                    "parameter": "Mode",
                    "baseline": "Original precomputed result",
                    "optimized": SCENARIO_LABELS.get(scenario, scenario),
                }
            ]
            for key, value in _ordered_param_items(params):
                rows.append(
                    {
                        "parameter": PARAMETER_LABELS.get(key, key),
                        "baseline": "-",
                        "optimized": value,
                    }
                )
            return rows

        if scenario == "baseline":
            return [
                {
                    "parameter": "Mode",
                    "value": "Original precomputed result",
                    "note": "No extra optimization hyperparameters are applied in baseline mode.",
                }
            ]

        best = self.get_best_params(metal, scenario, cobalt_mode)
        params = best.get("best_params", {})
        return [
            {
                "parameter": PARAMETER_LABELS.get(key, key),
                "value": value,
                "note": "Best metal-level hyperparameter" if index == 0 else "",
            }
            for index, (key, value) in enumerate(_ordered_param_items(params))
        ]

    def build_case_notes(self, metal: str, scenario: str, table_view: str, cobalt_mode: str = "mid") -> list[str]:
        del table_view
        notes = [
            f"Display result: {SCENARIO_LABELS.get(scenario, scenario)}.",
            "The website reads precomputed node / link / summary files directly from the current runtime data layout under data/.",
            "No sankey_algo-style recomputation is triggered when you refresh the view.",
            "Diagnostics stay hidden in guest mode and switch to stage-level optimization summaries in non-guest mode.",
        ]
        if metal == "Co":
            notes.append(f"Cobalt scenario: {str(cobalt_mode or 'mid').capitalize()}.")
        if scenario == "first_optimization":
            notes.append(
                "First Optimization is synchronized from the latest conversion_factor_optimization output into the published runtime snapshot before the Sankey is rendered."
            )
            notes.append(
                "Overview, stage outcomes, stage diagnostics, source-scaling rows, and coefficient tables summarize factor_A / factor_B / factor_G / factor_NN outputs without changing the rest of the site workflow."
            )
        if scenario != "baseline":
            best = self.get_best_params(metal, scenario, cobalt_mode)
            notes.append(
                f"{metal} {SCENARIO_LABELS.get(scenario, scenario)} improved {best.get('cases_improved', 0)} of {best.get('case_count', 0)} yearly cases."
            )
        else:
            notes.append("Original mode mirrors the current exported baseline result before optimization adjustments.")
        return notes


@lru_cache(maxsize=1)
def get_repository() -> OutputRepository:
    config = get_battery_site_config()
    local_output_root = config.root_dir / "output"
    original_data_root = (
        config.original_data_root
        if (config.original_data_root / "baseline").exists()
        else local_output_root
    )
    first_optimization_data_root = (
        config.first_optimization_data_root
        if (config.first_optimization_data_root / "optimized").exists()
        else local_output_root
    )
    first_optimization_diagnostics_root = (
        config.first_optimization_diagnostics_root
        if config.first_optimization_diagnostics_root.exists()
        else config.instance_dir / "conversion_factor_optimization" / "output"
    )
    return OutputRepository(
        original_data_root=original_data_root,
        first_optimization_data_root=first_optimization_data_root,
        first_optimization_diagnostics_root=first_optimization_diagnostics_root,
        version_output_root=config.output_versions_root,
    )

