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


OPTIMIZATION_SCENARIOS = ("pareto_optimal", "sn_minimum", "deviation_minimum")
OPTIMIZATION_DATA_DIRS = {
    "pareto_optimal": "pareto_optimal",
    "sn_minimum": "sn_minimum",
    "deviation_minimum": "deviation_minimum",
}
RESULT_MODE_ALIASES = {"first_optimization": "pareto_optimal"}
SCENARIOS = ("baseline", *OPTIMIZATION_SCENARIOS)
SCENARIO_LABELS = {
    "baseline": "Original",
    "pareto_optimal": "Multiobjective",
    "sn_minimum": "SN Minimum",
    "deviation_minimum": "Deviation Minimum",
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
    **{scenario: "optimized" for scenario in OPTIMIZATION_SCENARIOS},
}
METRIC_ORDER = [
    ("unknown_total", "Unknown Total"),
    ("non_source_total", "From Non-Source Countries"),
    ("non_target_total", "To Non-Target Countries"),
    ("structural_sink_total", "Structural Sink"),
    ("total_special", "Total Special"),
    ("total_regular", "Total Regular"),
]
STAGE_GROUP_STAGES = {
    "S1-S2-S3": ("S1", "S2", "S3"),
    "S3-S4-S5": ("S3", "S4", "S5"),
    "S5-S6-S7": ("S5", "S6", "S7"),
}
STAGE_SLUG_GROUPS = {
    "s1_s2_s3": "S1-S2-S3",
    "s3_s4_s5": "S3-S4-S5",
    "s5_s6_s7": "S5-S6-S7",
}
STAGE_GROUP_SLUGS = {value: key for key, value in STAGE_SLUG_GROUPS.items()}
STAGE_SLUG_TRANSITIONS = {
    "s1_s2_s3": "trade1",
    "s3_s4_s5": "trade2",
    "s5_s6_s7": "trade3",
}
COEFFICIENT_WORKBOOK_SPECS = {
    "PP": ("factor_c_pp", "optimized_c_pp", "source_country_id", "target_country_id"),
    "PN": ("factor_c_pn", "optimized_c_pn", "source_country_id", ""),
    "NP": ("factor_c_np", "optimized_c_np", "", "target_country_id"),
}
LINK_STAGE_GROUPS = {
    "S1": "S1-S2-S3",
    "S2": "S1-S2-S3",
    "S3": "S3-S4-S5",
    "S4": "S3-S4-S5",
    "S5": "S5-S6-S7",
    "S6": "S5-S6-S7",
    "S7": "S5-S6-S7",
}
UNKNOWN_BREAKDOWN_TYPES = (
    ("unknown_source", "Unknown Source"),
    ("unknown_destination", "Unknown Destination"),
    ("non_source", "From Non-Source Countries"),
    ("non_target", "To Non-Target Countries"),
    ("structural_sink", "Structural Sink"),
)
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


def is_optimization_scenario(scenario: str) -> bool:
    return scenario in OPTIMIZATION_SCENARIOS


def normalize_scenario(scenario: str) -> str:
    return RESULT_MODE_ALIASES.get(scenario, scenario)


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


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _stage_group_for_link(source_stage: Any, target_stage: Any) -> str:
    source_group = LINK_STAGE_GROUPS.get(str(source_stage or ""))
    if source_group:
        return source_group
    return LINK_STAGE_GROUPS.get(str(target_stage or ""), "Other")



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


def _ancestor_named(path: Path, name: str) -> Path | None:
    normalized = name.lower()
    for candidate in (path, *path.parents):
        if candidate.name.lower() == normalized:
            return candidate
    return None


def _resolve_selected_workbook_path(workbook_path: Path, project_root: Path | None = None) -> Path:
    if workbook_path.exists():
        return workbook_path

    root = (project_root or get_battery_site_config().root_dir).resolve()
    parts = workbook_path.parts
    lower_parts = [part.lower() for part in parts]
    candidates: list[Path] = []

    workspace_root = _ancestor_named(root, "website")
    if workspace_root and "website" in lower_parts:
        marker_index = lower_parts.index("website")
        tail = parts[marker_index + 1 :]
        if tail:
            candidates.append(workspace_root.joinpath(*tail))

    if "worktrees" in lower_parts:
        marker_index = lower_parts.index("worktrees")
        tail = parts[marker_index + 1 :]
        if tail:
            worktrees_root = root.parent if root.parent.name.lower() == "worktrees" else root.parent / "worktrees"
            candidates.append(worktrees_root.joinpath(*tail))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return workbook_path


def _first_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _version_sort_key(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if name.startswith("v") and name[1:].isdigit():
        return (int(name[1:]), name)
    return (-1, name)


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
    optimization_data_roots: dict[str, Path] | None = None
    optimization_diagnostics_roots: dict[str, Path] | None = None

    def __post_init__(self) -> None:
        self._case_csv_cache: dict[tuple[str, int, str, str, str], pd.DataFrame] = {}
        self._case_json_cache: dict[tuple[str, int, str, str, str], Any] = {}
        self._transition_frame_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._coefficient_frame_cache: dict[tuple[str, str, str], pd.DataFrame] = {}
        optimization_data_roots = self.optimization_data_roots or {}
        optimization_diagnostics_roots = self.optimization_diagnostics_roots or {}
        scenario_output_dirs = {
            scenario: optimization_data_roots.get(scenario, self.first_optimization_data_root)
            for scenario in OPTIMIZATION_SCENARIOS
        }
        self.scenario_output_dirs = {
            "baseline": self.original_data_root,
            **scenario_output_dirs,
        }
        self.scenario_comparison_dirs = {
            "baseline": self.original_data_root / "comparison",
            **{scenario: root / "comparison" for scenario, root in scenario_output_dirs.items()},
        }
        self.scenario_diagnostics_dirs = {
            scenario: optimization_diagnostics_roots.get(scenario, scenario_output_dirs[scenario] / "diagnostics")
            for scenario in OPTIMIZATION_SCENARIOS
        }
        self.comparison_dir = self.scenario_comparison_dirs["pareto_optimal"]
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
            scenario: pd.read_csv(self.scenario_comparison_dirs[scenario] / "comparison_summary.csv")
            for scenario in OPTIMIZATION_SCENARIOS
        }
        self.transition_frames = {}
        for scenario in OPTIMIZATION_SCENARIOS:
            transition_detail_path = self.scenario_comparison_dirs[scenario] / "optimized_transition_detail.csv"
            self.transition_frames[scenario] = (
                pd.read_csv(transition_detail_path).fillna("") if transition_detail_path.exists() else pd.DataFrame()
            )
        self.feasibility_by_scenario = {}
        for scenario in OPTIMIZATION_SCENARIOS:
            feasibility_path = self.scenario_comparison_dirs[scenario] / "feasibility_summary.json"
            if feasibility_path.exists():
                with feasibility_path.open("r", encoding="utf-8") as handle:
                    self.feasibility_by_scenario[scenario] = json.load(handle)
            else:
                self.feasibility_by_scenario[scenario] = {"best_params_by_metal": {}}
        self.cobalt_mode_results: dict[str, dict[str, Any]] = {}
        for scenario in OPTIMIZATION_SCENARIOS:
            results_path = self.scenario_comparison_dirs[scenario] / "cobalt_mode_results.json"
            if results_path.exists():
                with results_path.open("r", encoding="utf-8") as handle:
                    self.cobalt_mode_results[scenario] = json.load(handle)
            else:
                self.cobalt_mode_results[scenario] = {}
        self.selected_parameter_frames: dict[str, pd.DataFrame] = {}
        for scenario in OPTIMIZATION_SCENARIOS:
            selected_path = scenario_output_dirs[scenario] / "selected_stage_hyperparameters.csv"
            self.selected_parameter_frames[scenario] = (
                pd.read_csv(selected_path).fillna("") if selected_path.exists() else pd.DataFrame()
            )
        self.country_name_by_id: dict[int, str] = {}
        self.country_region_by_id: dict[int, str] = {}
        try:
            reference_file = load_dataset_config().get("referenceFile", "")
            if reference_file:
                reference_frame = load_reference_frame(reference_file)
                self.country_name_by_id = {
                    int(row.id): str(row.name).strip()
                    for row in reference_frame[["id", "name"]].itertuples(index=False)
                    if pd.notna(row.id) and str(row.name).strip()
                }
                self.country_region_by_id = {
                    int(row.id): str(row.region).strip() or "Unknown"
                    for row in reference_frame[["id", "region"]].itertuples(index=False)
                    if pd.notna(row.id)
                }
        except Exception:
            self.country_name_by_id = {}
            self.country_region_by_id = {}
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
        fallback = self.scenario_output_dirs.get("pareto_optimal", self.first_optimization_data_root)
        return candidate if candidate.exists() else fallback

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

    def _node_breakdown_totals(self, nodes: pd.DataFrame, stages: tuple[str, ...]) -> dict[str, float]:
        if nodes.empty or "stage" not in nodes:
            return {key: 0.0 for key, _label in UNKNOWN_BREAKDOWN_TYPES} | {"total_special": 0.0}

        working = nodes[nodes["stage"].astype(str).isin(stages)].copy()
        if working.empty:
            return {key: 0.0 for key, _label in UNKNOWN_BREAKDOWN_TYPES} | {"total_special": 0.0}

        values = _numeric_series(working, "value")
        kinds = working.get("kind", pd.Series("", index=working.index)).astype(str)
        is_unknown = _numeric_series(working, "is_unknown") > 0
        is_non_source = _numeric_series(working, "is_non_source") > 0
        is_non_target = _numeric_series(working, "is_non_target") > 0
        is_structural_sink = _numeric_series(working, "is_structural_sink") > 0

        return {
            "unknown_source": float(values[is_unknown & kinds.eq("source_special")].sum()),
            "unknown_destination": float(values[is_unknown & kinds.eq("sink_special")].sum()),
            "non_source": float(values[is_non_source].sum()),
            "non_target": float(values[is_non_target].sum()),
            "structural_sink": float(values[is_structural_sink].sum()),
            "total_special": float(values[kinds.ne("regular")].sum()),
        }

    def _regular_node_count(self, nodes: pd.DataFrame, stages: tuple[str, ...]) -> int:
        if nodes.empty or "stage" not in nodes:
            return 0
        working = nodes[nodes["stage"].astype(str).isin(stages)].copy()
        if working.empty:
            return 0
        kinds = working.get("kind", pd.Series("", index=working.index)).astype(str)
        regular = working[kinds.eq("regular")]
        if regular.empty:
            return 0
        label_column = "label" if "label" in regular else "key"
        labels = regular[label_column].astype(str).str.strip()
        return int(labels[labels.ne("")].nunique())

    def _selected_stage_records(
        self,
        metal: str,
        year: int,
        scenario: str,
    ) -> dict[str, dict[str, Any]]:
        frame = self.selected_parameter_frames.get(scenario, pd.DataFrame())
        if frame.empty or "metal" not in frame:
            return {}
        rows = frame[frame["metal"].astype(str).eq(metal)].copy()
        if "year" in rows:
            rows = rows[rows["year"].astype(str).eq(str(year))]
        if rows.empty:
            return {}
        records: dict[str, dict[str, Any]] = {}
        for record in rows.to_dict(orient="records"):
            stage_slug = str(record.get("stage_slug", "")).strip().lower()
            stage_group = STAGE_SLUG_GROUPS.get(stage_slug)
            if stage_group:
                records[stage_group] = record
        return records

    def _stage_group_comparison_rows(
        self,
        metal: str,
        year: int,
        scenario: str,
        cobalt_mode: str = "mid",
    ) -> list[dict[str, Any]]:
        baseline_nodes = self.load_case_csv(metal, year, "baseline", "nodes", cobalt_mode)
        optimized_nodes = self.load_case_csv(metal, year, scenario, "nodes", cobalt_mode)
        selected_records = self._selected_stage_records(metal, year, scenario)
        rows: list[dict[str, Any]] = []

        for stage_group, stages in STAGE_GROUP_STAGES.items():
            baseline_totals = self._node_breakdown_totals(baseline_nodes, stages)
            optimized_totals = self._node_breakdown_totals(optimized_nodes, stages)
            original_sn = baseline_totals["total_special"]
            optimized_sn = optimized_totals["total_special"]
            reduction = original_sn - optimized_sn
            reduction_pct = (reduction / original_sn) if abs(original_sn) > 1e-9 else 0.0
            record = selected_records.get(stage_group, {})
            raw_status = str(record.get("status", "")).strip().lower()
            if raw_status in {"success", "replaced"}:
                status = "success"
            elif raw_status == "not_replaced":
                status = "retained"
            else:
                status = raw_status or "recorded"

            rows.append(
                {
                    "Stage Group": stage_group,
                    "Status": status,
                    "Original SN": original_sn,
                    "Optimized SN": optimized_sn,
                    "Reduction Pct": reduction_pct,
                    "Countries": self._regular_node_count(optimized_nodes, stages),
                    "HS Codes": 1 if raw_status in {"success", "replaced"} else 0,
                    "c_pp Rows": 0,
                    "c_pn Rows": 0,
                    "c_np Rows": 0,
                    "Bound Hits": 0,
                    "Scaled Sources": 0,
                    "Overflow Before Scaling": 0,
                    "Special Total": optimized_totals["total_special"],
                    "Beta 1": record.get("beta_1", ""),
                    "Beta 2": record.get("beta_2", ""),
                    "Selection Type": record.get("selected_type", ""),
                    "Selection Reason": record.get("reason", ""),
                    "Stage Slug": record.get("stage_slug", STAGE_GROUP_SLUGS.get(stage_group, "")),
                    "Failure": "",
                }
            )
        return rows

    def get_unknown_breakdown_rows(
        self,
        metal: str,
        year: int,
        scenario: str,
        cobalt_mode: str = "mid",
    ) -> list[dict[str, Any]]:
        if not is_optimization_scenario(scenario):
            return []

        baseline_nodes = self.load_case_csv(metal, year, "baseline", "nodes", cobalt_mode)
        optimized_nodes = self.load_case_csv(metal, year, scenario, "nodes", cobalt_mode)
        rows: list[dict[str, Any]] = []

        for stage_group, stages in STAGE_GROUP_STAGES.items():
            baseline_totals = self._node_breakdown_totals(baseline_nodes, stages)
            optimized_totals = self._node_breakdown_totals(optimized_nodes, stages)
            stage_reduction = baseline_totals["total_special"] - optimized_totals["total_special"]

            for order, (key, label) in enumerate(UNKNOWN_BREAKDOWN_TYPES):
                original_value = baseline_totals[key]
                optimized_value = optimized_totals[key]
                reduction = original_value - optimized_value
                rows.append(
                    {
                        "stage_group": stage_group,
                        "type_key": key,
                        "unknown_type": label,
                        "original_value": original_value,
                        "optimized_value": optimized_value,
                        "reduction": reduction,
                        "change": optimized_value - original_value,
                        "reduction_pct": (reduction / original_value) if abs(original_value) > 1e-9 else 0.0,
                        "stage_special_original": baseline_totals["total_special"],
                        "stage_special_optimized": optimized_totals["total_special"],
                        "stage_special_reduction": stage_reduction,
                        "type_order": order,
                    }
                )

            rows.append(
                {
                    "stage_group": stage_group,
                    "type_key": "total_special",
                    "unknown_type": "Total Special Nodes",
                    "original_value": baseline_totals["total_special"],
                    "optimized_value": optimized_totals["total_special"],
                    "reduction": stage_reduction,
                    "change": optimized_totals["total_special"] - baseline_totals["total_special"],
                    "reduction_pct": (
                        stage_reduction / baseline_totals["total_special"]
                        if abs(baseline_totals["total_special"]) > 1e-9
                        else 0.0
                    ),
                    "stage_special_original": baseline_totals["total_special"],
                    "stage_special_optimized": optimized_totals["total_special"],
                    "stage_special_reduction": stage_reduction,
                    "type_order": len(UNKNOWN_BREAKDOWN_TYPES),
                }
            )

        return rows

    def get_trade_flow_compare_rows(
        self,
        metal: str,
        year: int,
        scenario: str,
        cobalt_mode: str = "mid",
    ) -> list[dict[str, Any]]:
        if not is_optimization_scenario(scenario):
            return []

        baseline_links = self.load_case_csv(metal, year, "baseline", "links", cobalt_mode)
        optimized_links = self.load_case_csv(metal, year, scenario, "links", cobalt_mode)

        def indexed(frame: pd.DataFrame) -> dict[tuple[str, str, str, str, str, str], float]:
            if frame.empty:
                return {}
            working = frame.copy()
            working["value"] = _numeric_series(working, "value")
            keys = ["source", "source_stage", "source_label", "target", "target_stage", "target_label"]
            for column in keys:
                if column not in working:
                    working[column] = ""
                working[column] = working[column].astype(str)
            grouped = working.groupby(keys, dropna=False)["value"].sum().reset_index()
            return {
                tuple(str(record[column]) for column in keys): float(record["value"])
                for record in grouped.to_dict(orient="records")
            }

        baseline_by_key = indexed(baseline_links)
        optimized_by_key = indexed(optimized_links)
        rows: list[dict[str, Any]] = []
        for key in sorted(set(baseline_by_key) | set(optimized_by_key)):
            source, source_stage, source_label, target, target_stage, target_label = key
            original_value = baseline_by_key.get(key, 0.0)
            optimized_value = optimized_by_key.get(key, 0.0)
            change = optimized_value - original_value
            if abs(original_value) <= 1e-9 and optimized_value > 1e-9:
                status = "New"
            elif original_value > 1e-9 and abs(optimized_value) <= 1e-9:
                status = "Removed"
            elif change < -1e-9:
                status = "Reduced"
            elif change > 1e-9:
                status = "Increased"
            else:
                status = "Flat"
            special_signal = "special:" in source or "special:" in target
            label_signal = any(
                token in f"{source_label} {target_label}".lower()
                for token in ("unknown", "non-", "unrelated")
            )
            rows.append(
                {
                    "stage_group": _stage_group_for_link(source_stage, target_stage),
                    "source_stage": source_stage,
                    "target_stage": target_stage,
                    "source_label": source_label,
                    "target_label": target_label,
                    "flow_type": "Unknown / special" if special_signal or label_signal else "Country flow",
                    "original_value": original_value,
                    "optimized_value": optimized_value,
                    "change": change,
                    "reduction": original_value - optimized_value,
                    "change_pct": (change / original_value) if abs(original_value) > 1e-9 else 0.0,
                    "status": status,
                }
            )
        rows.sort(key=lambda row: abs(float(row["change"])), reverse=True)
        return rows

    def get_comparison_row(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> dict[str, Any]:
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
        cache_key = (scenario, metal, cobalt_mode)
        if cache_key in self._coefficient_frame_cache:
            return self._coefficient_frame_cache[cache_key]
        candidate_paths: list[Path] = []
        for intermediate_dir in self._coefficient_intermediate_dirs(scenario):
            candidate_paths.extend(
                _intermediate_file_candidates(
                    intermediate_dir,
                    "first_optimization_coefficients.csv",
                    metal,
                    cobalt_mode,
                )
            )
            candidate_paths.extend(sorted(intermediate_dir.glob("*coefficients*.csv")))
        path = next((candidate for candidate in candidate_paths if candidate.exists()), None)
        frame = pd.read_csv(path).fillna("") if path is not None else self._load_selected_workbook_coefficients(scenario, metal)
        self._coefficient_frame_cache[cache_key] = frame
        return frame

    def _coefficient_intermediate_dirs(self, scenario: str) -> list[Path]:
        """Return coefficient search roots in runtime-preferred order.

        Older runtime bundles kept optimizer coefficient CSVs under
        `output_versions/<version>/output/intermediate` while newer bundles can
        expose scenario-specific diagnostics beside `app_data/<scenario>`.  The
        website should support both layouts because Render data updates are
        intentionally decoupled from code deploys.
        """
        candidates = [
            self.scenario_output_dirs[scenario] / "intermediate",
            self.scenario_diagnostics_dirs.get(scenario, Path()) / "intermediate",
            self.first_optimization_diagnostics_root / "intermediate",
        ]
        version_dirs = sorted(
            (path for path in self.version_output_root.glob("v*") if path.is_dir()),
            key=_version_sort_key,
            reverse=True,
        )
        candidates.extend(version_dir / "output" / "intermediate" for version_dir in version_dirs)

        seen: set[str] = set()
        resolved: list[Path] = []
        for candidate in candidates:
            key = str(candidate.resolve() if candidate.exists() else candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                resolved.append(candidate)
        return resolved

    def _load_selected_workbook_coefficients(self, scenario: str, metal: str) -> pd.DataFrame:
        """Build coefficient explorer rows from selected optimizer reports when CSV diagnostics are not bundled."""
        selected = self.selected_parameter_frames.get(scenario, pd.DataFrame())
        if selected.empty or "workbook_path" not in selected.columns:
            return pd.DataFrame()
        rows = selected[
            selected.get("metal", pd.Series("", index=selected.index)).astype(str).eq(metal)
            & selected.get("status", pd.Series("", index=selected.index)).astype(str).str.lower().eq("replaced")
        ].copy()
        if rows.empty:
            return pd.DataFrame()

        coefficient_rows: list[dict[str, Any]] = []
        for selected_record in rows.to_dict(orient="records"):
            workbook_path = _resolve_selected_workbook_path(Path(str(selected_record.get("workbook_path", "")).strip()))
            stage_slug = str(selected_record.get("stage_slug", "")).strip()
            transition = STAGE_SLUG_TRANSITIONS.get(stage_slug, "")
            if not workbook_path.exists() or not transition:
                continue
            try:
                sheet_frames = {
                    coefficient_class: pd.read_excel(workbook_path, sheet_name=sheet_name).fillna("")
                    for coefficient_class, (sheet_name, _value_column, _exporter_column, _importer_column) in COEFFICIENT_WORKBOOK_SPECS.items()
                }
            except Exception:
                continue

            exposure_totals: dict[str, float] = {}
            for sheet_frame in sheet_frames.values():
                if sheet_frame.empty:
                    continue
                for record in sheet_frame.to_dict(orient="records"):
                    hs_key = str(record.get("hs_code", "") or record.get("folder_name", "") or "")
                    exposure_totals[hs_key] = exposure_totals.get(hs_key, 0.0) + _safe_float(record.get("raw_trade_quantity_t"))

            for coefficient_class, sheet_frame in sheet_frames.items():
                if sheet_frame.empty:
                    continue
                _sheet_name, value_column, exporter_column, importer_column = COEFFICIENT_WORKBOOK_SPECS[coefficient_class]
                for record in sheet_frame.to_dict(orient="records"):
                    folder_name = str(record.get("folder_name", "") or "")
                    hs_key = str(record.get("hs_code", "") or folder_name)
                    optimized_value = _safe_float(record.get(value_column))
                    lower = _safe_float(record.get("Cmin"))
                    upper = _safe_float(record.get("Cmax"))
                    exposure = _safe_float(record.get("raw_trade_quantity_t"))
                    total_exposure = exposure_totals.get(hs_key, 0.0)
                    coefficient_rows.append(
                        {
                            "metal": metal,
                            "year": _safe_int(selected_record.get("year")),
                            "transition": transition,
                            "folder_name": folder_name,
                            "coefficient_class": coefficient_class,
                            "exporter": _safe_int(record.get(exporter_column)) if exporter_column else "",
                            "importer": _safe_int(record.get(importer_column)) if importer_column else "",
                            "coef_value": optimized_value,
                            "recommended_value": _safe_float(record.get("Crec")),
                            "lower_bound": lower,
                            "upper_bound": upper,
                            "hit_lower": int(abs(optimized_value - lower) <= 1e-9),
                            "hit_upper": int(abs(optimized_value - upper) <= 1e-9),
                            "exposure": exposure,
                            "exposure_share": (exposure / total_exposure) if abs(total_exposure) > 1e-9 else 0.0,
                        }
                    )
        return pd.DataFrame(coefficient_rows).fillna("") if coefficient_rows else pd.DataFrame()

    def get_transition_rows(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if not is_optimization_scenario(scenario):
            return []
        frame = self._load_transition_frame(scenario, metal, cobalt_mode)
        if frame.empty or not {"metal", "year"}.issubset(frame.columns):
            return []
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
            diagnostic_version = "optimization" if is_optimization_scenario(scenario) else "baseline"
            is_advanced = is_optimization_scenario(scenario) or bool(coefficient_summary)
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

    def _selected_parameter_rows(
        self,
        metal: str,
        scenario: str,
        cobalt_mode: str = "mid",
        year: int | None = None,
        compare: bool = False,
    ) -> list[dict[str, Any]]:
        del cobalt_mode
        frame = self.selected_parameter_frames.get(scenario, pd.DataFrame())
        if frame.empty:
            return []
        rows = frame[frame["metal"].astype(str).eq(metal)].copy()
        if year is not None and "year" in rows:
            rows = rows[rows["year"].astype(str).eq(str(year))]
        if rows.empty:
            return []

        stage_rank = {"s1_s2_s3": 0, "s3_s4_s5": 1, "s5_s6_s7": 2}
        rows["_stage_rank"] = rows.get("stage_slug", pd.Series("", index=rows.index)).astype(str).map(stage_rank).fillna(99)
        rows["_year_sort"] = pd.to_numeric(rows.get("year", pd.Series(0, index=rows.index)), errors="coerce").fillna(0)
        rows = rows.sort_values(["_year_sort", "_stage_rank"])

        output: list[dict[str, Any]] = [
            {
                "parameter": "Mode",
                **(
                    {"baseline": "Original precomputed result", "optimized": SCENARIO_LABELS.get(scenario, scenario)}
                    if compare
                    else {"value": SCENARIO_LABELS.get(scenario, scenario), "note": "Selected normalized optimizer export."}
                ),
            }
        ]
        for record in rows.to_dict(orient="records"):
            stage_slug = str(record.get("stage_slug", ""))
            stage_label = stage_slug.replace("_", "-").upper() if stage_slug else "Stage"
            row_year = str(record.get("year", "")).strip()
            prefix = f"{row_year} {stage_label}".strip() if year is None else stage_label
            values = [
                ("Status", record.get("status", "")),
                ("Beta 1", record.get("beta_1", "")),
                ("Beta 2", record.get("beta_2", "")),
                ("Optimized SN Total", record.get("optimized_SN_total", "")),
                ("Factor Deviation Weighted Mean", record.get("factor_dev_weighted_mean", "")),
                ("Selection Reason", record.get("reason", "")),
            ]
            for label, value in values:
                if value in ("", None):
                    continue
                item = {"parameter": f"{prefix} {label}"}
                if compare:
                    item.update({"baseline": "-", "optimized": value})
                else:
                    item.update({"value": value, "note": "Selected stage hyperparameter" if label in {"Beta 1", "Beta 2"} else ""})
                output.append(item)
        return output

    def get_producer_coefficient_rows(self, metal: str, year: int, scenario: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if scenario == "baseline":
            return []
        frame = self._load_coefficient_frame(scenario, metal, cobalt_mode)
        if frame.empty or not {"metal", "year"}.issubset(frame.columns):
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
                    "recommended_value": _safe_float(record.get("recommended_value")),
                    "lower_bound": _safe_float(record.get("lower_bound")),
                    "upper_bound": _safe_float(record.get("upper_bound")),
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
        if table_view == "compare" and scenario != "baseline":
            stage_rows = self._stage_group_comparison_rows(metal, year, scenario, cobalt_mode)
            supported_rows = [row for row in stage_rows if str(row.get("Status", "")).lower() == "success"] or stage_rows
            original_total = sum(_safe_float(row.get("Original SN")) for row in supported_rows)
            optimized_total = sum(_safe_float(row.get("Optimized SN")) for row in supported_rows)
            reduction = original_total - optimized_total
            reduction_pct = (reduction / original_total) if abs(original_total) > 1e-9 else 0.0
            coefficient_total = sum(
                _safe_int(row.get("c_pp Rows")) + _safe_int(row.get("c_pn Rows")) + _safe_int(row.get("c_np Rows"))
                for row in supported_rows
            )
            return [
                {"Metric": "Supported Stage Groups", "Value": f"{len(supported_rows)} / {len(stage_rows)}", "Note": ""},
                {"Metric": "Original SN Total", "Value": original_total, "Note": "Sum across selected stage-group diagnostics."},
                {"Metric": "Optimized SN Total", "Value": optimized_total, "Note": f"{SCENARIO_LABELS.get(scenario, scenario)} runtime snapshot."},
                {"Metric": "SN Reduction", "Value": reduction, "Note": ""},
                {"Metric": "SN Reduction Pct", "Value": reduction_pct, "Note": ""},
                {"Metric": "c_pp / c_pn / c_np Rows", "Value": coefficient_total, "Note": "Coefficient rows are shown when the selected optimizer export publishes coefficient diagnostics."},
                {"Metric": "Bound Hits", "Value": sum(_safe_int(row.get("Bound Hits")) for row in supported_rows), "Note": "Rows whose optimized coefficient equals Cmin or Cmax."},
                {"Metric": "Scaled Sources", "Value": sum(_safe_int(row.get("Scaled Sources")) for row in supported_rows), "Note": "Count of source-side scaling events recorded for the selected export."},
                {"Metric": "Overflow Before Scaling", "Value": sum(_safe_float(row.get("Overflow Before Scaling")) for row in supported_rows), "Note": ""},
                {"Metric": "Representative Special Total", "Value": sum(_safe_float(row.get("Special Total")) for row in supported_rows), "Note": ""},
            ]

        summary = self.get_summary_row(metal, year, scenario, cobalt_mode)
        return [{"metric": label, "value": summary[key]} for key, label in METRIC_ORDER]

    def build_stage_rows(self, metal: str, year: int, scenario: str, table_view: str, cobalt_mode: str = "mid") -> list[dict[str, Any]]:
        if table_view == "compare" and scenario != "baseline":
            return self._stage_group_comparison_rows(metal, year, scenario, cobalt_mode)

        return self.get_stage_rows(metal, year, scenario, cobalt_mode)

    def build_parameter_rows(
        self,
        metal: str,
        scenario: str,
        table_view: str,
        cobalt_mode: str = "mid",
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        if table_view == "compare" and scenario != "baseline":
            best = self.get_best_params(metal, scenario, cobalt_mode)
            params = best.get("best_params", {})
            runtime_rows = [
                {
                    "parameter": "Data Source",
                    "baseline": "Original precomputed result",
                    "optimized": f"{SCENARIO_LABELS.get(scenario, scenario)} selected optimizer export",
                    "note": "Analysis reads the active runtime bundle without exposing private file paths.",
                },
                {
                    "parameter": "Result Sync",
                    "baseline": "Original runtime snapshot",
                    "optimized": f"Published {SCENARIO_LABELS.get(scenario, scenario)} runtime snapshot",
                    "note": "Selected optimizer tables are synchronized into the current Sankey runtime format before rendering.",
                },
                {
                    "parameter": "Solver",
                    "baseline": "-",
                    "optimized": "Precomputed normalized optimization output",
                    "note": "Solver details are summarized from public runtime metadata only.",
                },
            ]
            if not params:
                selected_rows = self._selected_parameter_rows(metal, scenario, cobalt_mode, year, compare=True)
                if selected_rows:
                    return runtime_rows + selected_rows
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
            return runtime_rows + rows

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
        if not params:
            selected_rows = self._selected_parameter_rows(metal, scenario, cobalt_mode, year)
            if selected_rows:
                return selected_rows
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
            "Analysis stays hidden in guest mode and switches to stage-level optimization summaries in non-guest mode.",
        ]
        if metal == "Co":
            notes.append(f"Cobalt scenario: {str(cobalt_mode or 'mid').capitalize()}.")
        if is_optimization_scenario(scenario):
            notes.append(
                f"{SCENARIO_LABELS.get(scenario, scenario)} is served from the selected normalized optimizer export in the active runtime bundle."
            )
            notes.append(
                "Overview, stage outcomes, selected stage hyperparameters, and unknown-node movement compare original and optimized Sankey exports without changing the rest of the site workflow."
            )
        if scenario != "baseline":
            best = self.get_best_params(metal, scenario, cobalt_mode)
            case_count = best.get("case_count", 0)
            if case_count:
                notes.append(
                    f"{metal} {SCENARIO_LABELS.get(scenario, scenario)} improved {best.get('cases_improved', 0)} of {case_count} yearly cases."
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
    optimization_data_roots: dict[str, Path] = {}
    optimization_diagnostics_roots: dict[str, Path] = {}
    for scenario, directory_name in OPTIMIZATION_DATA_DIRS.items():
        scenario_root = config.data_dir / directory_name
        optimization_data_roots[scenario] = (
            scenario_root
            if (scenario_root / "optimized").exists()
            else first_optimization_data_root
        )
        scenario_diagnostics_root = scenario_root / "diagnostics"
        optimization_diagnostics_roots[scenario] = (
            scenario_diagnostics_root
            if scenario_diagnostics_root.exists()
            else first_optimization_diagnostics_root
        )
    return OutputRepository(
        original_data_root=original_data_root,
        first_optimization_data_root=first_optimization_data_root,
        first_optimization_diagnostics_root=first_optimization_diagnostics_root,
        version_output_root=config.output_versions_root,
        optimization_data_roots=optimization_data_roots,
        optimization_diagnostics_roots=optimization_diagnostics_roots,
    )
