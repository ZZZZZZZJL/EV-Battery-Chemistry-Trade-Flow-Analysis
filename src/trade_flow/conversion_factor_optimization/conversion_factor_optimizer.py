from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from trade_flow.baseline import core as baseline_core
from trade_flow.common.paths import get_project_paths
from trade_flow.conversion_factor_optimization import role_config


EPSILON = 1e-9


@dataclass(frozen=True)
class ObjectiveWeights:
    alpha: float = 1.0
    beta_pp: float = 0.02
    beta_pn: float = 0.01
    beta_np: float = 0.01


@dataclass(frozen=True)
class FolderTheoreticalConfig:
    hs_code: str | None
    cmin: float | None
    cmax: float | None
    crec: float | None
    note: str = ""
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class HSOptimizationCase:
    folder_name: str
    hs_code: str
    cmin: float
    cmax: float
    crec: float
    source_fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    source_countries: set[int]
    target_countries: set[int]
    pp_edges: dict[tuple[int, int], float]
    pn_totals: dict[int, float]
    np_edges: dict[tuple[int, int], float]
    np_totals: dict[int, float]
    ignored_other_total: float
    note: str


@dataclass(frozen=True)
class OptimizationCase:
    metal: str
    year: int
    stage_triplet: tuple[str, str, str]
    transition_key: str
    cobalt_mode: str
    context: Any
    hs_cases: tuple[HSOptimizationCase, ...]
    country_ids: tuple[int, ...]
    country_names: dict[int, str]
    iso3_map: dict[int, str]
    effective_supply: dict[int, float]
    effective_demand: dict[int, float]
    default_trade_need: dict[int, float]
    explicit_balance_map: dict[int, float]
    dataset_config: dict[str, Any]
    raw_import_root: Path
    project_root: Path
    website_root: Path


@dataclass(frozen=True)
class OptimizationResult:
    case: OptimizationCase
    output_dir: Path
    solver_backend: str
    solver_python: str
    summary_df: pd.DataFrame
    country_df: pd.DataFrame
    source_scale_df: pd.DataFrame
    c_pp_factor_df: pd.DataFrame
    c_pn_factor_df: pd.DataFrame
    c_np_factor_df: pd.DataFrame
    special_case_df: pd.DataFrame
    notes_df: pd.DataFrame


FOLDER_THEORETICAL_CONFIG: dict[str, FolderTheoreticalConfig] = {
    "1st_post_trade/Li_253090": FolderTheoreticalConfig(
        "253090",
        0.0,
        0.03,
        0.03,
        "Lithium S1-S2-S3 recommended factor from the memo.",
    ),
    "2nd_post_trade/Li_000000": FolderTheoreticalConfig(
        None,
        None,
        None,
        None,
        unsupported_reason=(
            "The memo does not provide an HS code or theoretical conversion factor for the "
            "synthetic Li S3-S4-S5 bucket Li_000000."
        ),
    ),
    "3rd_post_trade/Li_282520": FolderTheoreticalConfig("282520", 0.0, 0.4646, 0.165, "Lithium hydroxide pathway."),
    "3rd_post_trade/Li_283691": FolderTheoreticalConfig("283691", 0.0, 0.188, 0.188, "Lithium carbonate pathway."),
    "1st_post_trade/Ni_260400": FolderTheoreticalConfig("260400", 0.0, 0.25, 0.015, "Nickel concentrate pathway."),
    "2nd_post_trade/Ni_750110": FolderTheoreticalConfig("750110", 0.0, 0.75, 0.75),
    "2nd_post_trade/Ni_750120": FolderTheoreticalConfig("750120", 0.0, 0.75, 0.55),
    "2nd_post_trade/Ni_750300": FolderTheoreticalConfig("750300", 0.1, 1.0, 0.5),
    "2nd_post_trade/Ni_750400": FolderTheoreticalConfig("750400", 0.0, 1.0, 0.995),
    "3rd_post_trade/Ni_283324": FolderTheoreticalConfig("283324", 0.0, 0.379, 0.223, "Nickel sulphate pathway."),
    "1st_post_trade/Co_260500": FolderTheoreticalConfig("260500", 0.0, 0.5, 0.15),
    "2nd_post_trade/Co_282200": FolderTheoreticalConfig("282200", 0.0, 0.79, 0.329),
    "2nd_post_trade/Co_810520": FolderTheoreticalConfig("810520", 0.0, 1.0, 0.6),
    "2nd_post_trade/Co_810530": FolderTheoreticalConfig("810530", 0.0, 1.0, 0.6),
    "3rd_post_trade/Co_283329": FolderTheoreticalConfig("283329", 0.0, 0.38, 0.03, "Based on cobalt sulphate, following the memo."),
}


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _candidate_website_roots(explicit_root: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(Path(explicit_root))
    env_root = os.getenv("TRADE_FLOW_WEBSITE_ROOT") or os.getenv("TRADE_FLOW_OPT_WEBSITE_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(get_project_paths().project_root)
    return _dedupe_paths(candidates)


def _resolve_project_root(
    *,
    website_root: str | Path | None = None,
    project_root: str | Path | None = None,
) -> tuple[Path, Path]:
    if project_root is not None:
        resolved_project_root = Path(project_root).resolve()
        if not resolved_project_root.exists():
            raise FileNotFoundError(f"Project root does not exist: {resolved_project_root}")
        return resolved_project_root, resolved_project_root

    for candidate_root in _candidate_website_roots(website_root):
        candidate_root = candidate_root.resolve()
        if candidate_root.exists():
            return candidate_root, candidate_root
    searched = ", ".join(str(path) for path in _candidate_website_roots(website_root))
    raise FileNotFoundError(f"Could not find a usable project root. Searched: {searched}")


def _resolve_raw_import_root(website_root: Path, explicit_root: str | Path | None = None) -> Path:
    if explicit_root is not None:
        resolved = Path(explicit_root).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Raw import root does not exist: {resolved}")
        return resolved
    env_root = os.getenv("TRADE_FLOW_RAW_IMPORT_ROOT") or os.getenv("TRADE_FLOW_OPT_RAW_IMPORT_ROOT")
    if env_root:
        resolved = Path(env_root).resolve()
        if resolved.exists():
            return resolved
    runtime_candidate = website_root / "data" / "shared" / "trade" / "raw_import_by_partner"
    if runtime_candidate.exists():
        return runtime_candidate.resolve()
    candidate = (website_root.parent / "data").resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Default raw import root does not exist: {candidate}")
    return candidate


def _bootstrap_project_imports(project_root: Path) -> dict[str, Any]:
    repo_root = str(project_root)
    src_root = str(project_root / "src")
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return {
        "pipeline_v1": baseline_core,
        "role_config": role_config,
        "datasets": importlib.import_module("trade_flow.legacy_site.services.datasets"),
        "reference": importlib.import_module("trade_flow.legacy_site.services.reference"),
    }


def _sum_maps(*mappings: dict[int, float]) -> dict[int, float]:
    result: dict[int, float] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            numeric_key = int(key)
            result[numeric_key] = result.get(numeric_key, 0.0) + float(value)
    return {key: value for key, value in result.items() if abs(value) > EPSILON}


def _map_from_fields(inputs: Any, field_names: tuple[str, ...]) -> dict[int, float]:
    if not field_names:
        return {}
    return _sum_maps(*(dict(getattr(inputs, field_name, {})) for field_name in field_names))


def _nonzero_country_set(mapping: dict[int, float]) -> set[int]:
    return {int(country_id) for country_id, value in mapping.items() if abs(float(value)) > EPSILON}


def _effective_demand_map(context: Any) -> tuple[dict[int, float], dict[int, float]]:
    country_ids = set(context.target_totals) | set(context.trade_supply) | set(context.direct_local) | set(context.balance_map)
    default_trade_need = {
        int(country_id): max(
            float(context.target_totals.get(country_id, 0.0)) - float(context.direct_local.get(country_id, 0.0)),
            0.0,
        )
        for country_id in country_ids
    }
    effective_demand: dict[int, float] = {}
    for country_id in country_ids:
        supply = float(context.trade_supply.get(country_id, 0.0))
        if country_id in context.balance_map:
            demand = supply + float(context.balance_map[country_id])
        else:
            demand = default_trade_need.get(country_id, 0.0)
        if abs(demand) > EPSILON or abs(supply) > EPSILON or abs(default_trade_need.get(country_id, 0.0)) > EPSILON:
            effective_demand[int(country_id)] = float(demand)
    return effective_demand, default_trade_need


def _normalise_stage_triplet(stage_triplet: tuple[str, str, str] | list[str] | str) -> tuple[str, str, str]:
    if isinstance(stage_triplet, str):
        parts = [part.strip().upper() for part in stage_triplet.replace("-", ",").split(",") if part.strip()]
    else:
        parts = [str(part).strip().upper() for part in stage_triplet]
    if len(parts) != 3:
        raise ValueError(f"stage_triplet must contain exactly three stages, got: {stage_triplet}")
    return parts[0], parts[1], parts[2]


def _resolve_transition_spec(pipeline_v1: Any, metal: str, stage_triplet: tuple[str, str, str]) -> Any:
    for transition_spec in pipeline_v1.TRANSITIONS_BY_METAL[metal]:
        current_triplet = (
            transition_spec.source_stage.upper(),
            transition_spec.post_stage.upper(),
            transition_spec.target_stage.upper(),
        )
        if current_triplet == stage_triplet:
            return transition_spec
    available = [
        (spec.source_stage, spec.post_stage, spec.target_stage)
        for spec in pipeline_v1.TRANSITIONS_BY_METAL[metal]
    ]
    raise ValueError(f"Unsupported stage triplet for {metal}: {stage_triplet}. Available: {available}")


def _quantity_to_tonnes(frame: pd.DataFrame) -> pd.Series:
    if "qtyUnitAbbr" in frame.columns and "qty" in frame.columns:
        qty = pd.to_numeric(frame["qty"], errors="coerce")
        unit = frame["qtyUnitAbbr"].fillna("").astype(str).str.strip().str.lower()
        tonnes = pd.Series(np.nan, index=frame.index, dtype=float)
        tonnes.loc[unit.eq("kg")] = qty.loc[unit.eq("kg")] / 1000.0
        tonnes.loc[unit.eq("t")] = qty.loc[unit.eq("t")]
        if tonnes.notna().any():
            return tonnes.fillna(0.0)
    if "netWgt" in frame.columns:
        return pd.to_numeric(frame["netWgt"], errors="coerce").fillna(0.0) / 1000.0
    raise ValueError("Raw trade file is missing both qty/qtyUnitAbbr and netWgt columns.")


def _load_raw_import_map(raw_import_root: Path, year: int, hs_code: str) -> dict[tuple[int, int], float]:
    year_root = raw_import_root / f"UNComtrade_{year}_Import_ByPartner"
    if not year_root.exists():
        raise FileNotFoundError(f"Raw import folder does not exist: {year_root}")
    pattern = f"*_{hs_code}_M_{year}_partners.csv"
    flows: dict[tuple[int, int], float] = {}
    for file_path in sorted(year_root.rglob(pattern)):
        try:
            importer = int(file_path.name.split("_")[0])
        except ValueError:
            continue
        if importer == 0:
            continue
        frame = pd.read_csv(file_path, usecols=lambda col: col in {"partnerCode", "qtyUnitAbbr", "qty", "netWgt"})
        if "partnerCode" not in frame.columns:
            continue
        quantities = _quantity_to_tonnes(frame)
        partners = pd.to_numeric(frame["partnerCode"], errors="coerce")
        for exporter, quantity in zip(partners.tolist(), quantities.tolist()):
            if pd.isna(exporter):
                continue
            exporter_id = int(exporter)
            quantity_value = float(quantity)
            if exporter_id == 0 or quantity_value <= EPSILON:
                continue
            edge = (exporter_id, importer)
            flows[edge] = flows.get(edge, 0.0) + quantity_value
    return flows


def _classify_raw_edges(
    raw_map: dict[tuple[int, int], float],
    source_countries: set[int],
    target_countries: set[int],
) -> tuple[dict[tuple[int, int], float], dict[int, float], dict[tuple[int, int], float], dict[int, float], float]:
    pp_edges: dict[tuple[int, int], float] = {}
    pn_totals: dict[int, float] = {}
    np_edges: dict[tuple[int, int], float] = {}
    np_totals: dict[int, float] = {}
    ignored_other_total = 0.0
    for (exporter, importer), value in raw_map.items():
        if value <= EPSILON:
            continue
        if exporter in source_countries and importer in target_countries:
            pp_edges[(int(exporter), int(importer))] = float(value)
        elif exporter in source_countries and importer not in target_countries:
            pn_totals[int(exporter)] = pn_totals.get(int(exporter), 0.0) + float(value)
        elif exporter not in source_countries and importer in target_countries:
            np_edges[(int(exporter), int(importer))] = float(value)
            np_totals[int(importer)] = np_totals.get(int(importer), 0.0) + float(value)
        else:
            ignored_other_total += float(value)
    return pp_edges, pn_totals, np_edges, np_totals, ignored_other_total


def _build_case(
    *,
    metal: str,
    year: int,
    stage_triplet: tuple[str, str, str],
    cobalt_mode: str,
    website_root: Path,
    project_root: Path,
    raw_import_root: Path,
    modules: dict[str, Any],
    cmin_overrides: dict[str, float] | None,
) -> OptimizationCase:
    pipeline_v1 = modules["pipeline_v1"]
    active_role_config = modules["role_config"]
    dataset_config = modules["datasets"].load_dataset_config()
    inputs = pipeline_v1.load_year_inputs(metal, year)
    contexts = pipeline_v1.transition_contexts(metal, inputs, cobalt_mode=cobalt_mode)
    transition_spec = _resolve_transition_spec(pipeline_v1, metal, stage_triplet)
    transition_key = transition_spec.key
    context = contexts[transition_key]
    effective_demand, default_trade_need = _effective_demand_map(context)
    explicit_balance_map = {int(country_id): float(value) for country_id, value in context.balance_map.items()}

    hs_cases: list[HSOptimizationCase] = []
    all_country_ids: set[int] = set(context.source_totals) | set(context.trade_supply) | set(context.target_totals) | set(effective_demand)
    for folder_name in transition_spec.folder_names:
        theoretical = FOLDER_THEORETICAL_CONFIG.get(folder_name)
        if theoretical is None:
            raise ValueError(f"Missing theoretical conversion-factor configuration for folder: {folder_name}")
        if theoretical.unsupported_reason:
            raise ValueError(theoretical.unsupported_reason)
        role_spec = active_role_config.HS_ROLE_CONFIG.get(folder_name)
        if role_spec is None or not role_spec.optimize:
            raise ValueError(f"Folder {folder_name} is not configured as an optimisable HS bucket.")

        hs_code = str(theoretical.hs_code)
        cmin = float(theoretical.cmin)
        cmax = float(theoretical.cmax)
        crec = float(theoretical.crec)
        if cmin_overrides and hs_code in cmin_overrides:
            cmin = float(cmin_overrides[hs_code])
        if cmin > cmax + EPSILON:
            raise ValueError(f"Cmin exceeds Cmax for HS {hs_code}: {cmin} > {cmax}")
        if crec < cmin - EPSILON or crec > cmax + EPSILON:
            raise ValueError(f"Crec is outside the feasible interval for HS {hs_code}: {crec} not in [{cmin}, {cmax}]")

        source_map = _map_from_fields(inputs, role_spec.source_fields)
        target_map = _map_from_fields(inputs, role_spec.target_fields)
        source_countries = _nonzero_country_set(source_map)
        target_countries = _nonzero_country_set(target_map)
        raw_map = _load_raw_import_map(raw_import_root, year, hs_code)
        pp_edges, pn_totals, np_edges, np_totals, ignored_other_total = _classify_raw_edges(
            raw_map,
            source_countries,
            target_countries,
        )
        all_country_ids.update(source_countries)
        all_country_ids.update(target_countries)
        for exporter, importer in raw_map:
            all_country_ids.add(int(exporter))
            all_country_ids.add(int(importer))

        hs_cases.append(
            HSOptimizationCase(
                folder_name=folder_name,
                hs_code=hs_code,
                cmin=cmin,
                cmax=cmax,
                crec=crec,
                source_fields=tuple(role_spec.source_fields),
                target_fields=tuple(role_spec.target_fields),
                source_countries=source_countries,
                target_countries=target_countries,
                pp_edges=pp_edges,
                pn_totals=pn_totals,
                np_edges=np_edges,
                np_totals=np_totals,
                ignored_other_total=ignored_other_total,
                note=theoretical.note or role_spec.note,
            )
        )

    country_ids = tuple(sorted(all_country_ids))
    name_map, iso3_map, _color_map, _region_map = modules["reference"].load_reference_maps(
        dataset_config["referenceFile"],
        list(country_ids),
    )
    country_names = {country_id: name_map.get(country_id, f"Country {country_id}") for country_id in country_ids}
    return OptimizationCase(
        metal=metal,
        year=year,
        stage_triplet=stage_triplet,
        transition_key=transition_key,
        cobalt_mode=cobalt_mode,
        context=context,
        hs_cases=tuple(hs_cases),
        country_ids=country_ids,
        country_names=country_names,
        iso3_map={country_id: iso3_map.get(country_id, "") for country_id in country_ids},
        effective_supply={int(country_id): float(value) for country_id, value in context.trade_supply.items()},
        effective_demand=effective_demand,
        default_trade_need=default_trade_need,
        explicit_balance_map=explicit_balance_map,
        dataset_config=dataset_config,
        raw_import_root=raw_import_root,
        project_root=project_root,
        website_root=website_root,
    )


def _build_variable_order(case: OptimizationCase) -> dict[str, Any]:
    c_pp_keys: list[tuple[str, int, int]] = []
    c_pn_keys: list[tuple[str, int]] = []
    c_np_keys: list[tuple[str, int]] = []
    for hs_case in case.hs_cases:
        c_pp_keys.extend((hs_case.folder_name, exporter, importer) for exporter, importer in sorted(hs_case.pp_edges))
        c_pn_keys.extend((hs_case.folder_name, exporter) for exporter in sorted(hs_case.pn_totals))
        c_np_keys.extend((hs_case.folder_name, importer) for importer in sorted(hs_case.np_totals))

    c_pp_index = {key: position for position, key in enumerate(c_pp_keys)}
    c_pn_index = {key: position + len(c_pp_keys) for position, key in enumerate(c_pn_keys)}
    c_np_index = {
        key: position + len(c_pp_keys) + len(c_pn_keys)
        for position, key in enumerate(c_np_keys)
    }
    c_pp_dev_offset = len(c_pp_keys) + len(c_pn_keys) + len(c_np_keys)
    c_pn_dev_offset = c_pp_dev_offset + len(c_pp_keys)
    c_np_dev_offset = c_pn_dev_offset + len(c_pn_keys)
    c_pp_dev_index = {key: position + c_pp_dev_offset for position, key in enumerate(c_pp_keys)}
    c_pn_dev_index = {key: position + c_pn_dev_offset for position, key in enumerate(c_pn_keys)}
    c_np_dev_index = {key: position + c_np_dev_offset for position, key in enumerate(c_np_keys)}
    u_in_offset = c_np_dev_offset + len(c_np_keys)
    u_out_offset = u_in_offset + len(case.country_ids)
    return {
        "c_pp_keys": c_pp_keys,
        "c_pn_keys": c_pn_keys,
        "c_np_keys": c_np_keys,
        "c_pp_index": c_pp_index,
        "c_pn_index": c_pn_index,
        "c_np_index": c_np_index,
        "c_pp_dev_index": c_pp_dev_index,
        "c_pn_dev_index": c_pn_dev_index,
        "c_np_dev_index": c_np_dev_index,
        "u_in_offset": u_in_offset,
        "u_out_offset": u_out_offset,
        "variable_count": u_out_offset + len(case.country_ids),
    }


def _build_lp_problem(case: OptimizationCase, weights: ObjectiveWeights) -> tuple[dict[str, Any], dict[str, Any]]:
    order = _build_variable_order(case)
    country_row = {country_id: row_index for row_index, country_id in enumerate(case.country_ids)}
    variable_count = order["variable_count"]
    c = np.zeros(variable_count, dtype=float)
    bounds: list[tuple[float | None, float | None]] = [(0.0, None)] * variable_count
    hs_lookup = {hs_case.folder_name: hs_case for hs_case in case.hs_cases}

    for key in order["c_pp_keys"]:
        hs_case = hs_lookup[key[0]]
        index = order["c_pp_index"][key]
        bounds[index] = (hs_case.cmin, hs_case.cmax)
        c[order["c_pp_dev_index"][key]] = float(weights.beta_pp)
    for key in order["c_pn_keys"]:
        hs_case = hs_lookup[key[0]]
        index = order["c_pn_index"][key]
        bounds[index] = (hs_case.cmin, hs_case.cmax)
        c[order["c_pn_dev_index"][key]] = float(weights.beta_pn)
    for key in order["c_np_keys"]:
        hs_case = hs_lookup[key[0]]
        index = order["c_np_index"][key]
        bounds[index] = (hs_case.cmin, hs_case.cmax)
        c[order["c_np_dev_index"][key]] = float(weights.beta_np)
    for row_index, _country_id in enumerate(case.country_ids):
        c[order["u_in_offset"] + row_index] = float(weights.alpha)
        c[order["u_out_offset"] + row_index] = float(weights.alpha)

    a_eq = np.zeros((len(case.country_ids), variable_count), dtype=float)
    b_eq = np.zeros(len(case.country_ids), dtype=float)
    for row_index, country_id in enumerate(case.country_ids):
        a_eq[row_index, order["u_in_offset"] + row_index] = 1.0
        a_eq[row_index, order["u_out_offset"] + row_index] = -1.0
        supply = float(case.effective_supply.get(country_id, 0.0))
        demand = float(case.effective_demand.get(country_id, 0.0))
        b_eq[row_index] = demand - supply

    ub_rows: list[np.ndarray] = []
    ub_rhs: list[float] = []

    def add_deviation_constraints(
        variable_index: int,
        deviation_index: int,
        quantity: float,
        recommended_factor: float,
    ) -> None:
        if quantity <= EPSILON:
            return
        positive_row = np.zeros(variable_count, dtype=float)
        positive_row[variable_index] = float(quantity)
        positive_row[deviation_index] = -1.0
        ub_rows.append(positive_row)
        ub_rhs.append(float(quantity) * float(recommended_factor))

        negative_row = np.zeros(variable_count, dtype=float)
        negative_row[variable_index] = -float(quantity)
        negative_row[deviation_index] = -1.0
        ub_rows.append(negative_row)
        ub_rhs.append(-float(quantity) * float(recommended_factor))

    for hs_case in case.hs_cases:
        for (exporter, importer), quantity in hs_case.pp_edges.items():
            key = (hs_case.folder_name, exporter, importer)
            index = order["c_pp_index"][key]
            a_eq[country_row[importer], index] += float(quantity)
            a_eq[country_row[exporter], index] -= float(quantity)
            add_deviation_constraints(index, order["c_pp_dev_index"][key], float(quantity), hs_case.crec)
        for exporter, quantity in hs_case.pn_totals.items():
            key = (hs_case.folder_name, exporter)
            index = order["c_pn_index"][key]
            a_eq[country_row[exporter], index] -= float(quantity)
            add_deviation_constraints(index, order["c_pn_dev_index"][key], float(quantity), hs_case.crec)
        for (exporter, importer), quantity in hs_case.np_edges.items():
            key = (hs_case.folder_name, importer)
            index = order["c_np_index"][key]
            a_eq[country_row[importer], index] += float(quantity)
        for importer, quantity in hs_case.np_totals.items():
            key = (hs_case.folder_name, importer)
            add_deviation_constraints(
                order["c_np_index"][key],
                order["c_np_dev_index"][key],
                float(quantity),
                hs_case.crec,
            )
    a_ub = np.vstack(ub_rows) if ub_rows else np.zeros((0, variable_count), dtype=float)
    b_ub = np.asarray(ub_rhs, dtype=float) if ub_rhs else np.zeros(0, dtype=float)

    return {
        "c": c,
        "A_eq": a_eq,
        "b_eq": b_eq,
        "A_ub": a_ub,
        "b_ub": b_ub,
        "bounds": bounds,
    }, order


def _discover_solver_python(explicit_solver_python: str | None = None) -> str:
    candidates: list[str] = []
    if explicit_solver_python:
        candidates.append(explicit_solver_python)
    env_candidate = os.getenv("TRADE_FLOW_CFO_SOLVER_PYTHON") or os.getenv("TRADE_FLOW_OPT_SOLVER_PYTHON")
    if env_candidate:
        candidates.append(env_candidate)

    where_result = subprocess.run(["where", "python"], capture_output=True, text=True, check=False)
    if where_result.returncode == 0:
        candidates.extend(line.strip() for line in where_result.stdout.splitlines() if line.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    for candidate in deduped:
        probe = subprocess.run(
            [candidate, "-c", "import scipy, sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    raise RuntimeError(
        "Could not find a Python interpreter with scipy installed. "
        "Set TRADE_FLOW_CFO_SOLVER_PYTHON to an interpreter that can import scipy."
    )


def _solve_with_scipy_helper(problem: dict[str, Any], solver_python: str | None) -> tuple[np.ndarray, str, str]:
    helper_path = Path(__file__).resolve().parent / "_linprog_helper.py"
    payload = {
        "c": problem["c"].tolist(),
        "A_eq": problem["A_eq"].tolist(),
        "b_eq": problem["b_eq"].tolist(),
        "A_ub": problem["A_ub"].tolist(),
        "b_ub": problem["b_ub"].tolist(),
        "bounds": problem["bounds"],
    }
    resolved_python = _discover_solver_python(solver_python)
    completed = subprocess.run(
        [resolved_python, str(helper_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "External scipy helper failed.\n"
            f"Interpreter: {resolved_python}\n"
            f"stdout: {completed.stdout}\n"
            f"stderr: {completed.stderr}"
        )
    result = json.loads(completed.stdout)
    if not result["success"]:
        raise RuntimeError(f"LP solve failed: {result['message']}")
    return np.asarray(result["x"], dtype=float), "external_scipy", resolved_python


def _solve_linear_program(problem: dict[str, Any], solver_python: str | None = None) -> tuple[np.ndarray, str, str]:
    try:
        from scipy.optimize import linprog  # type: ignore

        result = linprog(
            c=problem["c"],
            A_ub=problem["A_ub"] if len(problem["b_ub"]) else None,
            b_ub=problem["b_ub"] if len(problem["b_ub"]) else None,
            A_eq=problem["A_eq"],
            b_eq=problem["b_eq"],
            bounds=problem["bounds"],
            method="highs",
        )
        if not result.success:
            raise RuntimeError(f"LP solve failed: {result.message}")
        return np.asarray(result.x, dtype=float), "local_scipy", sys.executable
    except ImportError:
        return _solve_with_scipy_helper(problem, solver_python)


def _extract_solution_maps(
    order: dict[str, Any],
    solution: np.ndarray,
) -> tuple[
    dict[tuple[str, int, int], float],
    dict[tuple[str, int], float],
    dict[tuple[str, int], float],
]:
    c_pp_values = {key: float(solution[index]) for key, index in order["c_pp_index"].items()}
    c_pn_values = {key: float(solution[index]) for key, index in order["c_pn_index"].items()}
    c_np_values = {key: float(solution[index]) for key, index in order["c_np_index"].items()}
    return c_pp_values, c_pn_values, c_np_values


def _baseline_value_maps(
    case: OptimizationCase,
) -> tuple[
    dict[tuple[str, int, int], float],
    dict[tuple[str, int], float],
    dict[tuple[str, int], float],
]:
    c_pp_values: dict[tuple[str, int, int], float] = {}
    c_pn_values: dict[tuple[str, int], float] = {}
    c_np_values: dict[tuple[str, int], float] = {}
    for hs_case in case.hs_cases:
        for exporter, importer in hs_case.pp_edges:
            c_pp_values[(hs_case.folder_name, exporter, importer)] = hs_case.crec
        for exporter in hs_case.pn_totals:
            c_pn_values[(hs_case.folder_name, exporter)] = hs_case.crec
        for importer in hs_case.np_totals:
            c_np_values[(hs_case.folder_name, importer)] = hs_case.crec
    return c_pp_values, c_pn_values, c_np_values


def _evaluate_case(
    case: OptimizationCase,
    c_pp_values: dict[tuple[str, int, int], float],
    c_pn_values: dict[tuple[str, int], float],
    c_np_values: dict[tuple[str, int], float],
) -> pd.DataFrame:
    pp_imports: dict[int, float] = {}
    np_imports: dict[int, float] = {}
    pp_exports: dict[int, float] = {}
    pn_exports: dict[int, float] = {}
    for hs_case in case.hs_cases:
        for (exporter, importer), quantity in hs_case.pp_edges.items():
            flow = float(quantity) * float(c_pp_values[(hs_case.folder_name, exporter, importer)])
            pp_imports[importer] = pp_imports.get(importer, 0.0) + flow
            pp_exports[exporter] = pp_exports.get(exporter, 0.0) + flow
        for exporter, quantity in hs_case.pn_totals.items():
            flow = float(quantity) * float(c_pn_values[(hs_case.folder_name, exporter)])
            pn_exports[exporter] = pn_exports.get(exporter, 0.0) + flow
        for (exporter, importer), quantity in hs_case.np_edges.items():
            flow = float(quantity) * float(c_np_values[(hs_case.folder_name, importer)])
            np_imports[importer] = np_imports.get(importer, 0.0) + flow

    rows: list[dict[str, Any]] = []
    for country_id in case.country_ids:
        supply = float(case.effective_supply.get(country_id, 0.0))
        demand = float(case.effective_demand.get(country_id, 0.0))
        pp_import_value = float(pp_imports.get(country_id, 0.0))
        np_import_value = float(np_imports.get(country_id, 0.0))
        pp_export_value = float(pp_exports.get(country_id, 0.0))
        pn_export_value = float(pn_exports.get(country_id, 0.0))
        import_value = pp_import_value + np_import_value
        export_value = pp_export_value + pn_export_value
        balance = supply + import_value - demand - export_value
        special_in = max(-balance, 0.0)
        special_out = max(balance, 0.0)
        if abs(special_in) <= EPSILON:
            special_in = 0.0
        if abs(special_out) <= EPSILON:
            special_out = 0.0
        if abs(balance) <= EPSILON:
            balance = 0.0
        rows.append(
            {
                "country_id": country_id,
                "country": case.country_names.get(country_id, f"Country {country_id}"),
                "iso3": case.iso3_map.get(country_id, ""),
                "P_s1": supply,
                "D_s3": demand,
                "PP_import": pp_import_value,
                "NP_import": np_import_value,
                "PP_export": pp_export_value,
                "PN_export": pn_export_value,
                "import_value": import_value,
                "export_value": export_value,
                "balance": balance,
                "special_in": special_in,
                "special_out": special_out,
                "total_special": special_in + special_out,
            }
        )
    return pd.DataFrame(rows)


def _merge_country_results(baseline_df: pd.DataFrame, optimized_df: pd.DataFrame) -> pd.DataFrame:
    merged = baseline_df.merge(
        optimized_df,
        on=["country_id", "country", "iso3", "P_s1", "D_s3"],
        suffixes=("_baseline", "_optimized"),
    )
    renamed = merged.rename(
        columns={
            "PP_import_baseline": "baseline_PP_import",
            "NP_import_baseline": "baseline_NP_import",
            "PP_export_baseline": "baseline_PP_export",
            "PN_export_baseline": "baseline_PN_export",
            "import_value_baseline": "baseline_import",
            "export_value_baseline": "baseline_export",
            "balance_baseline": "baseline_balance",
            "special_in_baseline": "baseline_special_in",
            "special_out_baseline": "baseline_special_out",
            "total_special_baseline": "baseline_total_special",
            "PP_import_optimized": "optimized_PP_import",
            "NP_import_optimized": "optimized_NP_import",
            "PP_export_optimized": "optimized_PP_export",
            "PN_export_optimized": "optimized_PN_export",
            "import_value_optimized": "optimized_import",
            "export_value_optimized": "optimized_export",
            "balance_optimized": "optimized_balance",
            "special_in_optimized": "optimized_special_in",
            "special_out_optimized": "optimized_special_out",
            "total_special_optimized": "optimized_total_special",
        }
    )
    numeric_columns = [
        "P_s1",
        "D_s3",
        "baseline_import",
        "baseline_export",
        "baseline_total_special",
        "optimized_import",
        "optimized_export",
        "optimized_total_special",
    ]
    mask = renamed[numeric_columns].abs().sum(axis=1) > EPSILON
    return renamed.loc[mask].reset_index(drop=True)


def _evaluate_source_scaling(
    case: OptimizationCase,
    c_pp_values: dict[tuple[str, int, int], float],
    c_pn_values: dict[tuple[str, int], float],
) -> pd.DataFrame:
    target_flows: dict[int, float] = {}
    non_target_flows: dict[int, float] = {}
    target_ids = _nonzero_country_set({int(country_id): float(value) for country_id, value in case.context.target_totals.items()})

    for hs_case in case.hs_cases:
        for (exporter, importer), quantity in hs_case.pp_edges.items():
            flow = float(quantity) * float(c_pp_values[(hs_case.folder_name, exporter, importer)])
            target_flows[exporter] = target_flows.get(exporter, 0.0) + flow
        for exporter, quantity in hs_case.pn_totals.items():
            flow = float(quantity) * float(c_pn_values[(hs_case.folder_name, exporter)])
            non_target_flows[exporter] = non_target_flows.get(exporter, 0.0) + flow

    rows: list[dict[str, Any]] = []
    for country_id in case.country_ids:
        trade_supply = float(case.effective_supply.get(country_id, 0.0))
        target_known_total = float(target_flows.get(country_id, 0.0))
        non_target_known_total = float(non_target_flows.get(country_id, 0.0))
        known_total = target_known_total + non_target_known_total
        scale_ratio = min(1.0, trade_supply / known_total) if known_total > EPSILON else 1.0
        scaled_target_total = target_known_total * scale_ratio
        scaled_non_target_total = non_target_known_total * scale_ratio
        scaled_known_total = scaled_target_total + scaled_non_target_total
        residual_self_flow = max(trade_supply - scaled_known_total, 0.0)
        rows.append(
            {
                "country_id": country_id,
                "country": case.country_names.get(country_id, f"Country {country_id}"),
                "iso3": case.iso3_map.get(country_id, ""),
                "trade_supply": trade_supply,
                "is_target_country": country_id in target_ids,
                "residual_link_bucket": "self_post_trade" if country_id in target_ids else "non_target",
                "target_known_total": target_known_total,
                "non_target_known_total": non_target_known_total,
                "known_total": known_total,
                "overflow_before_scaling": max(known_total - trade_supply, 0.0),
                "scale_ratio": scale_ratio,
                "scaled_target_known_total": scaled_target_total,
                "scaled_non_target_known_total": scaled_non_target_total,
                "scaled_known_total": scaled_known_total,
                "residual_self_flow": residual_self_flow,
                "scaled_down": scale_ratio < (1.0 - EPSILON),
            }
        )
    return pd.DataFrame(rows)


def _merge_source_scaling_results(baseline_df: pd.DataFrame, optimized_df: pd.DataFrame) -> pd.DataFrame:
    key_columns = ["country_id", "country", "iso3", "trade_supply", "is_target_country", "residual_link_bucket"]
    baseline_metrics = [column for column in baseline_df.columns if column not in key_columns]
    optimized_metrics = [column for column in optimized_df.columns if column not in key_columns]
    baseline_renamed = baseline_df.rename(columns={column: f"baseline_{column}" for column in baseline_metrics})
    optimized_renamed = optimized_df.rename(columns={column: f"optimized_{column}" for column in optimized_metrics})
    merged = baseline_renamed.merge(optimized_renamed, on=key_columns, how="inner")
    mask = merged[["trade_supply", "baseline_known_total", "optimized_known_total"]].abs().sum(axis=1) > EPSILON
    return merged.loc[mask].reset_index(drop=True)


def _build_factor_tables(
    case: OptimizationCase,
    c_pp_values: dict[tuple[str, int, int], float],
    c_pn_values: dict[tuple[str, int], float],
    c_np_values: dict[tuple[str, int], float],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    c_pp_columns = [
        "folder_name",
        "hs_code",
        "source_country_i",
        "source_country_id",
        "target_country_j",
        "target_country_id",
        "raw_trade_quantity_t",
        "Cmin",
        "Cmax",
        "Crec",
        "optimized_c_pp",
    ]
    c_pn_columns = [
        "folder_name",
        "hs_code",
        "source_country_i",
        "source_country_id",
        "raw_trade_quantity_t",
        "Cmin",
        "Cmax",
        "Crec",
        "optimized_c_pn",
    ]
    c_np_columns = [
        "folder_name",
        "hs_code",
        "target_country_j",
        "target_country_id",
        "raw_trade_quantity_t",
        "Cmin",
        "Cmax",
        "Crec",
        "optimized_c_np",
    ]
    c_pp_rows: list[dict[str, Any]] = []
    c_pn_rows: list[dict[str, Any]] = []
    c_np_rows: list[dict[str, Any]] = []
    for hs_case in case.hs_cases:
        for (exporter, importer), quantity in sorted(hs_case.pp_edges.items()):
            optimized_c_pp = float(c_pp_values[(hs_case.folder_name, exporter, importer)])
            c_pp_rows.append(
                {
                    "folder_name": hs_case.folder_name,
                    "hs_code": hs_case.hs_code,
                    "source_country_i": case.country_names.get(exporter, f"Country {exporter}"),
                    "source_country_id": exporter,
                    "target_country_j": case.country_names.get(importer, f"Country {importer}"),
                    "target_country_id": importer,
                    "raw_trade_quantity_t": float(quantity),
                    "Cmin": hs_case.cmin,
                    "Cmax": hs_case.cmax,
                    "Crec": hs_case.crec,
                    "optimized_c_pp": optimized_c_pp,
                }
            )
        for exporter, quantity in sorted(hs_case.pn_totals.items()):
            optimized_c_pn = float(c_pn_values[(hs_case.folder_name, exporter)])
            c_pn_rows.append(
                {
                    "folder_name": hs_case.folder_name,
                    "hs_code": hs_case.hs_code,
                    "source_country_i": case.country_names.get(exporter, f"Country {exporter}"),
                    "source_country_id": exporter,
                    "raw_trade_quantity_t": float(quantity),
                    "Cmin": hs_case.cmin,
                    "Cmax": hs_case.cmax,
                    "Crec": hs_case.crec,
                    "optimized_c_pn": optimized_c_pn,
                }
            )
        for importer, quantity in sorted(hs_case.np_totals.items()):
            optimized_c_np = float(c_np_values[(hs_case.folder_name, importer)])
            c_np_rows.append(
                {
                    "folder_name": hs_case.folder_name,
                    "hs_code": hs_case.hs_code,
                    "target_country_j": case.country_names.get(importer, f"Country {importer}"),
                    "target_country_id": importer,
                    "raw_trade_quantity_t": float(quantity),
                    "Cmin": hs_case.cmin,
                    "Cmax": hs_case.cmax,
                    "Crec": hs_case.crec,
                    "optimized_c_np": optimized_c_np,
                }
            )
    return (
        pd.DataFrame(c_pp_rows, columns=c_pp_columns),
        pd.DataFrame(c_pn_rows, columns=c_pn_columns),
        pd.DataFrame(c_np_rows, columns=c_np_columns),
    )


def _build_special_case_table(case: OptimizationCase) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for country_id in case.country_ids:
        source_total = float(case.context.source_totals.get(country_id, 0.0))
        trade_supply = float(case.effective_supply.get(country_id, 0.0))
        direct_local = float(case.context.direct_local.get(country_id, 0.0))
        target_total = float(case.context.target_totals.get(country_id, 0.0))
        default_need = float(case.default_trade_need.get(country_id, 0.0))
        effective_demand = float(case.effective_demand.get(country_id, 0.0))
        explicit_balance = case.explicit_balance_map.get(country_id)

        adjustments = [
            ("source_excluded_from_trade_supply", source_total - trade_supply),
            ("direct_local_bypass", direct_local),
            ("target_removed_by_direct_local", target_total - default_need),
            ("effective_target_adjustment", target_total - effective_demand),
        ]
        if explicit_balance is not None:
            default_balance = default_need - trade_supply
            adjustments.append(("explicit_balance_override", float(explicit_balance) - float(default_balance)))

        for adjustment_type, value in adjustments:
            if abs(float(value)) <= EPSILON:
                continue
            rows.append(
                {
                    "metal": case.metal,
                    "year": case.year,
                    "stage_triplet": "-".join(case.stage_triplet),
                    "country_id": country_id,
                    "country": case.country_names.get(country_id, f"Country {country_id}"),
                    "adjustment_type": adjustment_type,
                    "value": float(value),
                }
            )

    for hs_case in case.hs_cases:
        if hs_case.ignored_other_total <= EPSILON:
            continue
        rows.append(
            {
                "metal": case.metal,
                "year": case.year,
                "stage_triplet": "-".join(case.stage_triplet),
                "country_id": pd.NA,
                "country": "All countries",
                "adjustment_type": "ignored_non_source_non_target_trade_outside_nn",
                "value": float(hs_case.ignored_other_total),
            }
        )
    return pd.DataFrame(rows)


def _build_notes_table(case: OptimizationCase, weights: ObjectiveWeights, solver_backend: str, solver_python: str) -> pd.DataFrame:
    rows = [
        {
            "note_type": "formulation",
            "note": (
                "Current formulation: optimise PP, PN, and NP conversion factors against recommended "
                "trade flows while minimizing total unknown-node mass. Bounds are implemented as closed intervals."
            ),
        },
        {"note_type": "solver", "note": f"LP backend: {solver_backend}; solver interpreter: {solver_python}"},
        {
            "note_type": "paths",
            "note": json.dumps(
                {
                    "website_root": str(case.website_root),
                    "project_root": str(case.project_root),
                    "raw_import_root": str(case.raw_import_root),
                    "reference_file": case.dataset_config["referenceFile"],
                    "production_root": case.dataset_config["productionRoot"],
                },
                ensure_ascii=False,
            ),
        },
        {"note_type": "weights", "note": json.dumps(asdict(weights), ensure_ascii=False)},
        {
            "note_type": "source_scaling",
            "note": (
                "source_scaling.csv follows the Sankey source-side rule: "
                "scale_ratio = min(1, trade_supply / known_total), where known_total is the sum of target-bound "
                "known links plus source-to-non-target known links before residual self/non-target fill."
            ),
        },
    ]
    for hs_case in case.hs_cases:
        rows.append(
            {
                "note_type": f"hs_{hs_case.hs_code}",
                "note": (
                    f"{hs_case.folder_name}: bounds=[{hs_case.cmin:.6f}, {hs_case.cmax:.6f}], "
                    f"Crec={hs_case.crec:.6f}. {hs_case.note}"
                ),
            }
        )
    return pd.DataFrame(rows)


def _write_outputs(
    *,
    case: OptimizationCase,
    weights: ObjectiveWeights,
    solver_backend: str,
    solver_python: str,
    country_df: pd.DataFrame,
    source_scale_df: pd.DataFrame,
    c_pp_factor_df: pd.DataFrame,
    c_pn_factor_df: pd.DataFrame,
    c_np_factor_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    special_case_df: pd.DataFrame,
    output_root: Path,
) -> tuple[Path, pd.DataFrame]:
    triplet_slug = "_".join(stage.lower() for stage in case.stage_triplet)
    case_output_dir = output_root / case.metal / str(case.year) / triplet_slug
    case_output_dir.mkdir(parents=True, exist_ok=True)
    notes_df = _build_notes_table(case, weights, solver_backend, solver_python)

    country_df.to_csv(case_output_dir / "country_results.csv", index=False)
    source_scale_df.to_csv(case_output_dir / "source_scaling.csv", index=False)
    c_pp_factor_df.to_csv(case_output_dir / "factor_c_pp.csv", index=False)
    c_pn_factor_df.to_csv(case_output_dir / "factor_c_pn.csv", index=False)
    c_np_factor_df.to_csv(case_output_dir / "factor_c_np.csv", index=False)
    summary_df.to_csv(case_output_dir / "summary.csv", index=False)
    special_case_df.to_csv(case_output_dir / "special_case_adjustments.csv", index=False)
    notes_df.to_csv(case_output_dir / "notes.csv", index=False)
    workbook_path = case_output_dir / "conversion_factor_optimization_report.xlsx"
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        country_df.to_excel(writer, sheet_name="country_results", index=False)
        source_scale_df.to_excel(writer, sheet_name="source_scaling", index=False)
        c_pp_factor_df.to_excel(writer, sheet_name="factor_c_pp", index=False)
        c_pn_factor_df.to_excel(writer, sheet_name="factor_c_pn", index=False)
        c_np_factor_df.to_excel(writer, sheet_name="factor_c_np", index=False)
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        special_case_df.to_excel(writer, sheet_name="special_cases", index=False)
        notes_df.to_excel(writer, sheet_name="notes", index=False)
    return case_output_dir, notes_df


def run_conversion_factor_optimization(
    metal: str,
    year: int,
    stage_triplet: tuple[str, str, str] | list[str] | str,
    *,
    website_root: str | Path | None = None,
    project_root: str | Path | None = None,
    raw_import_root: str | Path | None = None,
    output_root: str | Path | None = None,
    cobalt_mode: str = "mid",
    cmin_overrides: dict[str, float] | None = None,
    objective_weights: ObjectiveWeights | None = None,
    solver_python: str | None = None,
) -> OptimizationResult:
    resolved_stage_triplet = _normalise_stage_triplet(stage_triplet)
    weights = objective_weights or ObjectiveWeights()
    if metal not in {"Li", "Ni", "Co"}:
        raise ValueError(f"Unsupported metal: {metal}")

    resolved_website_root, resolved_project_root = _resolve_project_root(
        website_root=website_root,
        project_root=project_root,
    )
    resolved_raw_import_root = _resolve_raw_import_root(resolved_website_root, explicit_root=raw_import_root)
    modules = _bootstrap_project_imports(resolved_project_root)
    case = _build_case(
        metal=metal,
        year=int(year),
        stage_triplet=resolved_stage_triplet,
        cobalt_mode=cobalt_mode,
        website_root=resolved_website_root,
        project_root=resolved_project_root,
        raw_import_root=resolved_raw_import_root,
        modules=modules,
        cmin_overrides=cmin_overrides,
    )

    problem, order = _build_lp_problem(case, weights)
    solution, solver_backend, resolved_solver_python = _solve_linear_program(problem, solver_python=solver_python)
    optimized_a, optimized_b, optimized_g = _extract_solution_maps(order, solution)
    baseline_a, baseline_b, baseline_g = _baseline_value_maps(case)
    baseline_eval = _evaluate_case(case, baseline_a, baseline_b, baseline_g)
    optimized_eval = _evaluate_case(case, optimized_a, optimized_b, optimized_g)
    country_df = _merge_country_results(baseline_eval, optimized_eval)
    baseline_source_scale = _evaluate_source_scaling(case, baseline_a, baseline_b)
    optimized_source_scale = _evaluate_source_scaling(case, optimized_a, optimized_b)
    source_scale_df = _merge_source_scaling_results(baseline_source_scale, optimized_source_scale)
    c_pp_factor_df, c_pn_factor_df, c_np_factor_df = _build_factor_tables(
        case,
        optimized_a,
        optimized_b,
        optimized_g,
    )
    special_case_df = _build_special_case_table(case)

    baseline_total = float(country_df["baseline_total_special"].sum())
    optimized_total = float(country_df["optimized_total_special"].sum())
    reduction_ratio = ((baseline_total - optimized_total) / baseline_total) if baseline_total > EPSILON else np.nan
    summary_df = pd.DataFrame(
        [
            {
                "metal": case.metal,
                "year": case.year,
                "stage_triplet": "-".join(case.stage_triplet),
                "transition_key": case.transition_key,
                "cobalt_mode": case.cobalt_mode,
                "baseline_SN_total": baseline_total,
                "optimized_SN_total": optimized_total,
                "reduction_ratio": reduction_ratio,
                "number_of_countries": len(case.country_ids),
                "number_of_c_pp_variables": len(order["c_pp_keys"]),
                "number_of_c_pn_variables": len(order["c_pn_keys"]),
                "number_of_c_np_variables": len(order["c_np_keys"]),
                "solver_backend": solver_backend,
                "solver_python": resolved_solver_python,
            }
        ]
    )

    default_output_root = get_project_paths().conversion_factor_optimization_output_root
    resolved_output_root = Path(output_root).resolve() if output_root is not None else default_output_root
    case_output_dir, notes_df = _write_outputs(
        case=case,
        weights=weights,
        solver_backend=solver_backend,
        solver_python=resolved_solver_python,
        country_df=country_df,
        source_scale_df=source_scale_df,
        c_pp_factor_df=c_pp_factor_df,
        c_pn_factor_df=c_pn_factor_df,
        c_np_factor_df=c_np_factor_df,
        summary_df=summary_df,
        special_case_df=special_case_df,
        output_root=resolved_output_root,
    )

    return OptimizationResult(
        case=case,
        output_dir=case_output_dir,
        solver_backend=solver_backend,
        solver_python=resolved_solver_python,
        summary_df=summary_df,
        country_df=country_df,
        source_scale_df=source_scale_df,
        c_pp_factor_df=c_pp_factor_df,
        c_pn_factor_df=c_pn_factor_df,
        c_np_factor_df=c_np_factor_df,
        special_case_df=special_case_df,
        notes_df=notes_df,
    )

