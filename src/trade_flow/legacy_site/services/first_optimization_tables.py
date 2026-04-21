from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


EPSILON = 1e-9
STAGE_TRIPLET_ORDER = ("S1-S2-S3", "S3-S4-S5", "S5-S6-S7")
STAGE_TRIPLET_TO_KEY = {
    "S1-S2-S3": "trade1",
    "S3-S4-S5": "trade2",
    "S5-S6-S7": "trade3",
}
KEY_TO_STAGE_TRIPLET = {value: key for key, value in STAGE_TRIPLET_TO_KEY.items()}
STAGE_FOLDER_NAMES = {
    "S1-S2-S3": "s1_s2_s3",
    "S3-S4-S5": "s3_s4_s5",
    "S5-S6-S7": "s5_s6_s7",
}


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
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _value_or_blank(value: Any) -> Any:
    return value if value not in (None, "") else ""


def _final_error_line(raw: Any) -> str:
    lines = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _bound_status(value: float, lower: float, upper: float) -> str:
    if abs(value - lower) <= 1e-9:
        return "Lower"
    if abs(value - upper) <= 1e-9:
        return "Upper"
    return "Interior"


def _transition_sort_key(value: str) -> int:
    order = {"trade1": 0, "trade2": 1, "trade3": 2}
    return order.get(value, len(order))


def _weights_signature(weights: dict[str, Any]) -> str:
    ordered = ["alpha", "beta_pp", "beta_pn", "beta_np", "beta_nn"]
    pairs = [f"{key}={weights[key]}" for key in ordered if key in weights]
    return ", ".join(pairs)


@dataclass
class FirstOptimizationTableSource:
    root_dir: Path
    country_name_by_id: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.output_root = self.root_dir / "output"
        self.batch_summary_path = self.root_dir / "batch_run_summary.csv"
        self.available = self.output_root.exists() and self.batch_summary_path.exists()
        self._case_cache: dict[tuple[str, int, str, str], pd.DataFrame] = {}
        if self.available:
            self.batch_frame = pd.read_csv(self.batch_summary_path).fillna("")
        else:
            self.batch_frame = pd.DataFrame()

    def _case_dir(self, metal: str, year: int, stage_triplet: str) -> Path:
        return self.output_root / metal / str(year) / STAGE_FOLDER_NAMES[stage_triplet]

    def _load_case_csv(self, metal: str, year: int, stage_triplet: str, filename: str) -> pd.DataFrame:
        cache_key = (metal, year, stage_triplet, filename)
        if cache_key in self._case_cache:
            return self._case_cache[cache_key]
        path = self._case_dir(metal, year, stage_triplet) / filename
        frame = pd.read_csv(path).fillna("") if path.exists() else pd.DataFrame()
        self._case_cache[cache_key] = frame
        return frame

    def _stage_rows(self, metal: str, year: int) -> list[dict[str, Any]]:
        if self.batch_frame.empty:
            return []
        rows = self.batch_frame[
            (self.batch_frame["metal"].astype(str) == metal) & (self.batch_frame["year"].astype(str) == str(year))
        ].to_dict(orient="records")
        by_stage = {str(row.get("stage_triplet", "")): row for row in rows}
        return [by_stage[stage] for stage in STAGE_TRIPLET_ORDER if stage in by_stage]

    def _preferred_stage_triplet(self, metal: str, year: int | None) -> str | None:
        years = [year] if year is not None else sorted({int(value) for value in self.batch_frame.get("year", [])}, reverse=True)
        for candidate_year in years:
            for row in self._stage_rows(metal, candidate_year):
                if str(row.get("status", "")).lower() == "success":
                    return str(row.get("stage_triplet", ""))
            for row in self._stage_rows(metal, candidate_year):
                stage_triplet = str(row.get("stage_triplet", ""))
                if stage_triplet:
                    return stage_triplet
        return None

    def _parameter_notes(self, metal: str, year: int | None) -> pd.DataFrame:
        if self.batch_frame.empty:
            return pd.DataFrame()
        preferred_year = year if year is not None else max(int(value) for value in self.batch_frame["year"].tolist())
        frames: list[pd.DataFrame] = []
        for stage_triplet in STAGE_TRIPLET_ORDER:
            notes = self._load_case_csv(metal, preferred_year, stage_triplet, "notes.csv")
            if notes.empty:
                continue
            tagged = notes.copy()
            tagged["stage_triplet"] = stage_triplet
            frames.append(tagged)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _stage_case_summary(self, metal: str, year: int, stage_triplet: str) -> dict[str, Any]:
        country_results = self._load_case_csv(metal, year, stage_triplet, "country_results.csv")
        factor_a = self._load_case_csv(metal, year, stage_triplet, "factor_A.csv")
        factor_b = self._load_case_csv(metal, year, stage_triplet, "factor_B.csv")
        factor_g = self._load_case_csv(metal, year, stage_triplet, "factor_G.csv")
        factor_nn = self._load_case_csv(metal, year, stage_triplet, "factor_NN.csv")
        source_scaling = self._load_case_csv(metal, year, stage_triplet, "source_scaling.csv")
        special_cases = self._load_case_csv(metal, year, stage_triplet, "special_case_adjustments.csv")

        country_ids: set[int] = set()
        if not country_results.empty and "country_id" in country_results.columns:
            country_ids = {
                _safe_int(value)
                for value in country_results["country_id"].tolist()
                if str(value).strip() and _safe_int(value) > 0
            }
        for frame, columns in (
            (factor_a, ("source_country_id", "target_country_id")),
            (factor_b, ("source_country_id",)),
            (factor_g, ("target_country_id",)),
            (factor_nn, ("source_country_id",)),
        ):
            if frame.empty:
                continue
            for column in columns:
                if column not in frame.columns:
                    continue
                for value in frame[column].tolist():
                    numeric = _safe_int(value)
                    if numeric > 0:
                        country_ids.add(numeric)

        hs_codes: set[str] = set()
        hs_exposure: dict[str, float] = {}
        lower_hits = 0
        upper_hits = 0
        a_count = int(len(factor_a))
        b_count = int(len(factor_b))
        g_count = int(len(factor_g))
        nn_count = int(len(factor_nn))
        for frame, value_column in (
            (factor_a, "optimized_A_ij"),
            (factor_b, "optimized_B_i"),
            (factor_g, "optimized_G_j"),
            (factor_nn, "optimized_NN_i"),
        ):
            if frame.empty:
                continue
            for record in frame.to_dict(orient="records"):
                hs_code = str(record.get("hs_code", "") or "").strip()
                if hs_code:
                    hs_codes.add(hs_code)
                    hs_exposure[hs_code] = hs_exposure.get(hs_code, 0.0) + _safe_float(record.get("raw_trade_quantity_t"))
                value = _safe_float(record.get(value_column))
                lower = _safe_float(record.get("Cmin"))
                upper = _safe_float(record.get("Cmax"))
                status = _bound_status(value, lower, upper)
                if status == "Lower":
                    lower_hits += 1
                elif status == "Upper":
                    upper_hits += 1

        special_items: list[dict[str, Any]] = []
        special_total = 0.0
        special_type_count = 0
        if not special_cases.empty:
            working = special_cases.copy()
            working["value"] = pd.to_numeric(working.get("value", 0.0), errors="coerce").fillna(0.0)
            if "adjustment_type" in working.columns:
                grouped = (
                    working.groupby("adjustment_type", dropna=False)["value"]
                    .sum()
                    .reset_index()
                    .sort_values("value", ascending=False)
                )
                special_type_count = int(len(grouped))
                for record in grouped.to_dict(orient="records")[:4]:
                    special_items.append(
                        {
                            "label": str(record.get("adjustment_type", "")).replace("_", " "),
                            "value": _safe_float(record.get("value")),
                        }
                    )
            group_columns = [column for column in ("country_id", "country") if column in working.columns]
            if group_columns:
                per_country = (
                    working.groupby(group_columns, dropna=False)["value"]
                    .apply(lambda series: float(series.abs().max()))
                    .reset_index(name="representative_value")
                )
                special_total = float(per_country["representative_value"].sum())
            else:
                special_total = float(working["value"].abs().sum())

        top_hs_items = [
            {"label": hs_code, "value": value}
            for hs_code, value in sorted(hs_exposure.items(), key=lambda item: item[1], reverse=True)[:5]
        ]

        scaled_source_count = 0
        overflow_total = 0.0
        worst_scale_ratio = 1.0
        residual_self_total = 0.0
        scaling_items: list[dict[str, Any]] = []
        if not source_scaling.empty:
            working = source_scaling.copy()
            working["optimized_overflow_before_scaling"] = pd.to_numeric(
                working.get("optimized_overflow_before_scaling", 0.0), errors="coerce"
            ).fillna(0.0)
            working["optimized_scale_ratio"] = pd.to_numeric(
                working.get("optimized_scale_ratio", 1.0), errors="coerce"
            ).fillna(1.0)
            working["optimized_residual_self_flow"] = pd.to_numeric(
                working.get("optimized_residual_self_flow", 0.0), errors="coerce"
            ).fillna(0.0)
            scaled_mask = working.get("optimized_scaled_down", "").astype(str).str.lower().eq("true")
            scaled_source_count = int(scaled_mask.sum())
            overflow_total = float(working["optimized_overflow_before_scaling"].sum())
            residual_self_total = float(working["optimized_residual_self_flow"].sum())
            if "optimized_known_total" in working:
                known_total = pd.to_numeric(working["optimized_known_total"], errors="coerce").fillna(0.0)
                active_rows = working.loc[known_total > EPSILON]
            else:
                active_rows = working
            if not active_rows.empty:
                worst_scale_ratio = float(active_rows["optimized_scale_ratio"].min())
            top_scaled = working.sort_values(
                ["optimized_overflow_before_scaling", "optimized_scale_ratio"],
                ascending=[False, True],
            ).head(4)
            for record in top_scaled.to_dict(orient="records"):
                country = str(record.get("country", "") or _safe_int(record.get("country_id")))
                overflow_value = _safe_float(record.get("optimized_overflow_before_scaling"))
                if overflow_value <= EPSILON and str(record.get("optimized_scaled_down", "")).lower() != "true":
                    continue
                scaling_items.append(
                    {
                        "label": country,
                        "value": overflow_value,
                        "note": f"scale={_safe_float(record.get('optimized_scale_ratio')):.3f}",
                    }
                )

        return {
            "country_count": len(country_ids),
            "hs_code_count": len(hs_codes),
            "a_count": a_count,
            "b_count": b_count,
            "g_count": g_count,
            "nn_count": nn_count,
            "coefficient_row_count": a_count + b_count + g_count + nn_count,
            "lower_hit_count": lower_hits,
            "upper_hit_count": upper_hits,
            "bound_hit_count": lower_hits + upper_hits,
            "special_total": special_total,
            "special_type_count": special_type_count,
            "special_items": special_items,
            "top_hs_items": top_hs_items,
            "scaled_source_count": scaled_source_count,
            "overflow_total": overflow_total,
            "worst_scale_ratio": worst_scale_ratio,
            "residual_self_total": residual_self_total,
            "scaling_items": scaling_items,
        }

    def comparison_row(self, metal: str, year: int) -> dict[str, Any]:
        rows = self._stage_rows(metal, year)
        supported = [row for row in rows if str(row.get("status", "")).lower() == "success"]
        baseline_total = sum(_safe_float(row.get("baseline_SN_total")) for row in supported)
        optimized_total = sum(_safe_float(row.get("optimized_SN_total")) for row in supported)
        reduction = baseline_total - optimized_total
        reduction_pct = (reduction / baseline_total) if abs(baseline_total) > 1e-9 else 0.0
        return {
            "metal": metal,
            "year": year,
            "unknown_total_baseline": baseline_total,
            "unknown_total_optimized": optimized_total,
            "unknown_reduction": reduction,
            "unknown_reduction_pct": reduction_pct,
            "total_special_baseline": baseline_total,
            "total_special_optimized": optimized_total,
            "special_reduction": reduction,
        }

    def metric_rows(self, metal: str, year: int) -> list[dict[str, Any]]:
        rows = self._stage_rows(metal, year)
        if not rows:
            return []
        supported = [row for row in rows if str(row.get("status", "")).lower() == "success"]
        unsupported = [row for row in rows if str(row.get("status", "")).lower() != "success"]
        summaries = {
            str(row.get("stage_triplet", "")): self._stage_case_summary(metal, year, str(row.get("stage_triplet", "")))
            for row in supported
        }

        baseline_total = sum(_safe_float(row.get("baseline_SN_total")) for row in supported)
        optimized_total = sum(_safe_float(row.get("optimized_SN_total")) for row in supported)
        reduction = baseline_total - optimized_total
        reduction_pct = (reduction / baseline_total) if abs(baseline_total) > 1e-9 else 0.0
        a_total = sum(summary["a_count"] for summary in summaries.values())
        b_total = sum(summary["b_count"] for summary in summaries.values())
        g_total = sum(summary["g_count"] for summary in summaries.values())
        nn_total = sum(summary["nn_count"] for summary in summaries.values())
        hs_total = sum(summary["hs_code_count"] for summary in summaries.values())
        bound_hits = sum(summary["bound_hit_count"] for summary in summaries.values())
        special_total = sum(summary["special_total"] for summary in summaries.values())
        scaled_sources = sum(summary["scaled_source_count"] for summary in summaries.values())
        overflow_total = sum(summary["overflow_total"] for summary in summaries.values())
        solver_backend = next((str(row.get("solver_backend", "")) for row in supported if str(row.get("solver_backend", "")).strip()), "-")
        solver_python = next((str(row.get("solver_python", "")) for row in supported if str(row.get("solver_python", "")).strip()), "-")
        unsupported_stages = ", ".join(str(row.get("stage_triplet", "")) for row in unsupported) or "-"

        return [
            {"Metric": "Supported Stage Groups", "Value": f"{len(supported)} / {len(rows)}", "Note": unsupported_stages if unsupported else ""},
            {"Metric": "Original SN Total", "Value": baseline_total, "Note": "Sum across supported stage groups only."},
            {"Metric": "Optimized SN Total", "Value": optimized_total, "Note": "Sum across supported stage groups only."},
            {"Metric": "SN Reduction", "Value": reduction, "Note": ""},
            {"Metric": "SN Reduction Pct", "Value": reduction_pct, "Note": ""},
            {"Metric": "HS Codes Across Supported Stages", "Value": hs_total, "Note": "Stage-level total; the same HS code can appear in multiple stage groups."},
            {"Metric": "A / B / G / NN Rows", "Value": f"{a_total} / {b_total} / {g_total} / {nn_total}", "Note": f"{a_total + b_total + g_total + nn_total} coefficient rows in total."},
            {"Metric": "Bound Hits", "Value": bound_hits, "Note": "Rows whose optimized coefficient equals Cmin or Cmax."},
            {"Metric": "Scaled Sources", "Value": scaled_sources, "Note": "Exporter rows where the Sankey source-side rule scales known outbound links back to trade_supply."},
            {"Metric": "Overflow Before Scaling", "Value": overflow_total, "Note": "Sum of optimized known flow that exceeded trade_supply before Sankey scaling."},
            {"Metric": "Representative Special Total", "Value": special_total, "Note": "Per-country representative amount; mirrored bookkeeping rows are not double-counted."},
            {"Metric": "Solver Backend", "Value": solver_backend, "Note": ""},
            {"Metric": "Solver Interpreter", "Value": solver_python, "Note": ""},
        ]

    def stage_rows(self, metal: str, year: int) -> list[dict[str, Any]]:
        stage_rows: list[dict[str, Any]] = []
        for row in self._stage_rows(metal, year):
            stage_triplet = str(row.get("stage_triplet", ""))
            summary = self._stage_case_summary(metal, year, stage_triplet)
            status = str(row.get("status", ""))
            successful = status.lower() == "success"
            stage_rows.append(
                {
                    "Stage Group": stage_triplet,
                    "Status": status,
                    "Original SN": _value_or_blank(_safe_float(row.get("baseline_SN_total")) if successful else ""),
                    "Optimized SN": _value_or_blank(_safe_float(row.get("optimized_SN_total")) if successful else ""),
                    "Reduction Pct": _value_or_blank(_safe_float(row.get("reduction_ratio")) if successful else ""),
                    "Countries": summary["country_count"],
                    "HS Codes": summary["hs_code_count"],
                    "A Rows": summary["a_count"],
                    "B Rows": summary["b_count"],
                    "G Rows": summary["g_count"],
                    "NN Rows": summary["nn_count"],
                    "Bound Hits": summary["bound_hit_count"],
                    "Scaled Sources": summary["scaled_source_count"],
                    "Overflow Before Scaling": summary["overflow_total"],
                    "Special Total": summary["special_total"],
                    "Failure": _final_error_line(row.get("note")) if not successful else "",
                }
            )
        return stage_rows

    def parameter_rows(self, metal: str, year: int | None) -> list[dict[str, Any]]:
        notes = self._parameter_notes(metal, year)
        rows: list[dict[str, Any]] = [
            {
                "Parameter": "Data Source",
                "Value": "conversion_factor_optimization",
                "Note": "Diagnostics read the latest conversion-factor optimizer output directly.",
            },
            {
                "Parameter": "Result Sync",
                "Value": "conversion_factor_optimization -> published First Optimization snapshot",
                "Note": "First Optimization Sankey files are converted into the runtime snapshot format before rendering.",
            },
            {
                "Parameter": "Special Handling",
                "Value": "Direct bypass / unrelated routing stays outside the LP balance",
                "Note": "Stage Diagnostics summarize these adjustments whenever they are present.",
            },
        ]
        if notes.empty:
            return rows

        note_records = notes.to_dict(orient="records")
        note_by_type = {str(record.get("note_type", "")): str(record.get("note", "")) for record in note_records}
        solver_note = note_by_type.get("solver", "")
        if solver_note:
            rows.append({"Parameter": "Solver", "Value": solver_note, "Note": ""})

        weights = _json_dict(note_by_type.get("weights"))
        if weights:
            weight_notes = {
                "alpha": "Primary SN reduction weight.",
                "beta_pp": "Penalty on PP edge-level coefficient movement.",
                "beta_pn": "Penalty on PN exporter-level coefficient movement.",
                "beta_np": "Penalty on NP importer-level coefficient movement.",
                "beta_nn": "Penalty on NN exporter-level coefficient movement.",
            }
            for key in ("alpha", "beta_pp", "beta_pn", "beta_np", "beta_nn"):
                if key in weights:
                    rows.append({"Parameter": key, "Value": weights[key], "Note": weight_notes.get(key, "Objective weight")})

        formulation_note = note_by_type.get("formulation", "")
        if formulation_note:
            rows.append({"Parameter": "Bounds", "Value": "Closed intervals [Cmin, Cmax]", "Note": formulation_note})

        scaling_note = note_by_type.get("source_scaling", "")
        if scaling_note:
            rows.append({"Parameter": "Source Scaling", "Value": "Sankey source-side scaling enabled", "Note": scaling_note})

        hs_rule_rows = [str(record.get("note", "")) for record in note_records if str(record.get("note_type", "")).startswith("hs_")]
        hs_rule_count = len(hs_rule_rows)
        if hs_rule_count:
            rows.append(
                {
                    "Parameter": "HS Memo Rules",
                    "Value": hs_rule_count,
                    "Note": hs_rule_rows[0],
                }
            )
        return rows

    def transition_rows(self, metal: str, year: int) -> list[dict[str, Any]]:
        transition_rows: list[dict[str, Any]] = []
        for stage_row in self._stage_rows(metal, year):
            stage_triplet = str(stage_row.get("stage_triplet", ""))
            transition_key = STAGE_TRIPLET_TO_KEY.get(stage_triplet, stage_triplet.lower())
            status = str(stage_row.get("status", "") or "")
            successful = status.lower() == "success"
            summary = self._stage_case_summary(metal, year, stage_triplet)
            notes = self._load_case_csv(metal, year, stage_triplet, "notes.csv")
            note_records = notes.to_dict(orient="records") if not notes.empty else []
            note_by_type = {str(record.get("note_type", "")): str(record.get("note", "")) for record in note_records}
            hs_rule_rows = [str(record.get("note", "")) for record in note_records if str(record.get("note_type", "")).startswith("hs_")]
            reduction = _safe_float(stage_row.get("reduction_ratio"))
            failure_note = _final_error_line(stage_row.get("note"))
            bound_share = (
                f"{summary['bound_hit_count']}/{summary['coefficient_row_count']}"
                if summary["coefficient_row_count"]
                else "0/0"
            )

            if not successful:
                signal_label = "Unsupported"
                signal_class = "negative"
            elif reduction > 1e-9:
                signal_label = "Reduced"
                signal_class = "positive"
            elif reduction < -1e-9:
                signal_label = "Higher"
                signal_class = "negative"
            else:
                signal_label = "Flat"
                signal_class = "neutral"

            setup_items = []
            solver_note = note_by_type.get("solver", "")
            if solver_note:
                setup_items.append({"label": "Solver", "value": solver_note})
            weights = _json_dict(note_by_type.get("weights"))
            if weights:
                setup_items.append({"label": "Weights", "value": _weights_signature(weights)})
            formulation_note = note_by_type.get("formulation", "")
            if formulation_note:
                setup_items.append({"label": "Bounds", "value": "Closed intervals", "note": formulation_note})
            scaling_note = note_by_type.get("source_scaling", "")
            if scaling_note:
                setup_items.append({"label": "Source scaling", "value": "Enabled", "note": scaling_note})
            if hs_rule_rows:
                setup_items.append({"label": "HS memo rules", "value": len(hs_rule_rows), "note": hs_rule_rows[0]})

            special_panel_items = [
                {"label": "Representative total", "value": summary["special_total"]},
                {"label": "Adjustment types", "value": summary["special_type_count"]},
                *summary["special_items"],
            ]
            scaling_panel_items = [
                {"label": "Scaled sources", "value": summary["scaled_source_count"]},
                {"label": "Overflow before scaling", "value": summary["overflow_total"]},
                {"label": "Worst scale ratio", "value": summary["worst_scale_ratio"]},
                {"label": "Residual self / non-target fill", "value": summary["residual_self_total"]},
                *summary["scaling_items"],
            ]

            transition_rows.append(
                {
                    "transition": transition_key,
                    "transition_display": stage_triplet,
                    "folder_name": STAGE_FOLDER_NAMES.get(stage_triplet, stage_triplet.lower()),
                    "folder_display": "Stage-Level Diagnostic",
                    "card_title": "Stage-Level Diagnostic",
                    "folder_group": "conversion_factor_optimization",
                    "diagnostic_kind": "first_optimization",
                    "signal_label": signal_label,
                    "signal_class": signal_class,
                    "card_note": (
                        failure_note
                        if failure_note
                        else f"{summary['hs_code_count']} HS codes | {summary['country_count']} countries | {summary['special_type_count']} special handling types"
                    ),
                    "has_signal": successful and reduction > 0,
                    "diagnostic_pills": [
                        {"label": "Original SN", "value": _safe_float(stage_row.get("baseline_SN_total")) if successful else "", "tone": "unknown"},
                        {"label": "Optimized SN", "value": _safe_float(stage_row.get("optimized_SN_total")) if successful else "", "tone": "neutral"},
                        {"label": "Reduction Pct", "value": reduction if successful else "", "tone": "source"},
                        {"label": "Bound Hits", "value": bound_share, "tone": "target"},
                        {"label": "Scaled Sources", "value": summary["scaled_source_count"], "tone": "neutral"},
                    ],
                    "diagnostic_panels": [
                        {
                            "title": "Outcome",
                            "subtitle": "Stage-triplet optimization result recorded by conversion_factor_optimization and synchronized into First Optimization",
                            "items": [
                                {"label": "Status", "value": status},
                                {"label": "Countries", "value": summary["country_count"]},
                                {"label": "Original SN", "value": _safe_float(stage_row.get("baseline_SN_total")) if successful else ""},
                                {"label": "Optimized SN", "value": _safe_float(stage_row.get("optimized_SN_total")) if successful else ""},
                                {"label": "Reduction Pct", "value": reduction if successful else ""},
                                {"label": "Failure", "value": failure_note if not successful else ""},
                            ],
                            "emptyText": "No stage-level optimization outcome was recorded.",
                        },
                        {
                            "title": "Coefficient Coverage",
                            "subtitle": "A / B / G / NN rows emitted for this stage group",
                            "items": [
                                {"label": "HS codes", "value": summary["hs_code_count"]},
                                {"label": "A rows", "value": summary["a_count"]},
                                {"label": "B rows", "value": summary["b_count"]},
                                {"label": "G rows", "value": summary["g_count"]},
                                {"label": "NN rows", "value": summary["nn_count"]},
                                {"label": "Total rows", "value": summary["coefficient_row_count"]},
                            ],
                            "emptyText": "No coefficient rows were recorded for this stage group.",
                        },
                        {
                            "title": "Sankey Scaling",
                            "subtitle": "How the synchronized First Optimization flows are scaled back to trade_supply before residual self / non-target fill",
                            "items": scaling_panel_items,
                            "emptyText": "No source-scaling rows were recorded for this stage group.",
                        },
                        {
                            "title": "Bounds",
                            "subtitle": "How often optimized coefficients sit on Cmin or Cmax",
                            "items": [
                                {"label": "Lower hits", "value": summary["lower_hit_count"]},
                                {"label": "Upper hits", "value": summary["upper_hit_count"]},
                                {"label": "Bound hits", "value": summary["bound_hit_count"]},
                                {"label": "Interior rows", "value": summary["coefficient_row_count"] - summary["bound_hit_count"]},
                            ],
                            "emptyText": "No bound activity was recorded for this stage group.",
                        },
                        {
                            "title": "Special Handling",
                            "subtitle": "Representative excluded volume by country; mirrored bookkeeping rows are not double-counted",
                            "items": special_panel_items,
                            "emptyText": "No special-case adjustments were recorded for this stage group.",
                        },
                        {
                            "title": "Top HS Exposure",
                            "subtitle": "Largest raw-trade HS codes contributing to this stage-group run",
                            "items": summary["top_hs_items"],
                            "emptyText": "No HS exposure rows were recorded for this stage group.",
                        },
                        {
                            "title": "Run Setup",
                            "subtitle": "Solver, weights, bounds, and source-scaling notes carried by the latest optimizer output",
                            "items": setup_items,
                            "emptyText": "No setup notes were recorded for this stage group.",
                        },
                    ],
                }
            )
        transition_rows.sort(key=lambda row: _transition_sort_key(str(row.get("transition", ""))))
        return transition_rows

    def producer_coefficient_rows(self, metal: str, year: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for stage_triplet in STAGE_TRIPLET_ORDER:
            transition_key = STAGE_TRIPLET_TO_KEY[stage_triplet]
            factor_frames = {
                "A": self._load_case_csv(metal, year, stage_triplet, "factor_A.csv"),
                "B": self._load_case_csv(metal, year, stage_triplet, "factor_B.csv"),
                "G": self._load_case_csv(metal, year, stage_triplet, "factor_G.csv"),
                "NN": self._load_case_csv(metal, year, stage_triplet, "factor_NN.csv"),
            }
            exposure_totals: dict[str, float] = {}
            for frame in factor_frames.values():
                if frame.empty:
                    continue
                for record in frame.to_dict(orient="records"):
                    hs_code = str(record.get("hs_code", "") or "")
                    exposure_totals[hs_code] = exposure_totals.get(hs_code, 0.0) + _safe_float(record.get("raw_trade_quantity_t"))

            for coefficient_class, frame in factor_frames.items():
                if frame.empty:
                    continue
                value_column = {"A": "optimized_A_ij", "B": "optimized_B_i", "G": "optimized_G_j", "NN": "optimized_NN_i"}[coefficient_class]
                for record in frame.to_dict(orient="records"):
                    hs_code = str(record.get("hs_code", "") or "")
                    exposure = _safe_float(record.get("raw_trade_quantity_t"))
                    total_exposure = exposure_totals.get(hs_code, 0.0)
                    coef_value = _safe_float(record.get(value_column))
                    lower = _safe_float(record.get("Cmin"))
                    upper = _safe_float(record.get("Cmax"))
                    if coefficient_class == "A":
                        producer_scope = str(record.get("source_country_i", "") or self.country_name_by_id.get(_safe_int(record.get("source_country_id")), "-"))
                        partner_scope = str(record.get("target_country_j", "") or self.country_name_by_id.get(_safe_int(record.get("target_country_id")), "-"))
                    elif coefficient_class == "B":
                        producer_scope = str(record.get("source_country_i", "") or self.country_name_by_id.get(_safe_int(record.get("source_country_id")), "-"))
                        partner_scope = "Source-side balance"
                    elif coefficient_class == "G":
                        producer_scope = str(record.get("target_country_j", "") or self.country_name_by_id.get(_safe_int(record.get("target_country_id")), "-"))
                        partner_scope = "Target-side balance"
                    else:
                        producer_scope = str(record.get("source_country_i", "") or self.country_name_by_id.get(_safe_int(record.get("source_country_id")), "-"))
                        partner_scope = "Target-country exporter to non-target destinations"

                    rows.append(
                        {
                            "transition": transition_key,
                            "transition_display": stage_triplet,
                            "hs_code": hs_code,
                            "coefficient_class": coefficient_class,
                            "producer_scope": producer_scope,
                            "partner_scope": partner_scope,
                            "coef_value": coef_value,
                            "bounds": f"[{lower:.3f}, {upper:.3f}]",
                            "bound_status": _bound_status(coef_value, lower, upper),
                            "exposure": exposure,
                            "exposure_share": (exposure / total_exposure) if abs(total_exposure) > 1e-9 else 0.0,
                        }
                    )
        rows.sort(
            key=lambda row: (
                _transition_sort_key(str(row.get("transition", ""))),
                str(row.get("hs_code", "")),
                str(row.get("coefficient_class", "")),
                str(row.get("producer_scope", "")),
            )
        )
        return rows
