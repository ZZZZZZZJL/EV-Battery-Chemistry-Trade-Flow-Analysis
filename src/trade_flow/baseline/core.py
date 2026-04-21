from __future__ import annotations

import csv
import importlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


# Core paths / 核心路径配置
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "output"
BASELINE_OUTPUT_ROOT = OUTPUT_ROOT / "baseline"
OPTIMIZED_OUTPUT_ROOT = OUTPUT_ROOT / "optimized"
COMPARISON_OUTPUT_ROOT = OUTPUT_ROOT / "comparison"
SPREADSHEET_OUTPUT_ROOT = OUTPUT_ROOT / "spreadsheet"
DATA_ROOT = PROJECT_ROOT / "data" / "shared"
TRADE_ROOT = DATA_ROOT / "trade"

METALS = ("Li", "Ni", "Co")
YEARS = (2020, 2021, 2022, 2023, 2024)
DEFAULT_COBALT_MODE = "mid"
EPSILON = 1e-9


@dataclass(frozen=True)
class HyperParameters:
    mirror_weight: float
    lag_weight: float
    hub_threshold: float
    reexport_cap: float
    priority_country_count: int
    scale_lower: float
    scale_upper: float
    scale_step: float
    scale_passes: int
    deviation_weight: float
    non_source_weight: float
    non_target_weight: float

    def scale_values(self) -> list[float]:
        values: list[float] = []
        current = self.scale_lower
        while current <= self.scale_upper + 1e-9:
            values.append(round(current, 6))
            current += self.scale_step
        if 1.0 not in values:
            values.append(1.0)
        return sorted(set(values))


@dataclass(frozen=True)
class TransitionSpec:
    key: str
    source_stage: str
    post_stage: str
    target_stage: str
    folder_names: tuple[str, ...]
    input_fields: tuple[str, ...]


@dataclass(frozen=True)
class TransitionContext:
    key: str
    source_stage: str
    post_stage: str
    target_stage: str
    source_totals: dict[int, float]
    trade_supply: dict[int, float]
    direct_local: dict[int, float]
    balance_map: dict[int, float]
    target_totals: dict[int, float]
    folder_names: tuple[str, ...]
    input_fields: tuple[str, ...]


TRANSITIONS_BY_METAL = {
    "Li": (
        TransitionSpec("trade1", "S1", "S2", "S3", ("1st_post_trade/Li_253090",), ("trade1",)),
        TransitionSpec("trade2", "S3", "S4", "S5", ("2nd_post_trade/Li_000000",), ("trade2",)),
        TransitionSpec(
            "trade3",
            "S5",
            "S6",
            "S7",
            ("3rd_post_trade/Li_282520", "3rd_post_trade/Li_283691"),
            ("trade3_hydroxide", "trade3_carbonate"),
        ),
    ),
    "Ni": (
        TransitionSpec("trade1", "S1", "S2", "S3", ("1st_post_trade/Ni_260400",), ("trade1",)),
        TransitionSpec(
            "trade2",
            "S3",
            "S4",
            "S5",
            (
                "2nd_post_trade/Ni_750110",
                "2nd_post_trade/Ni_750120",
                "2nd_post_trade/Ni_750300",
                "2nd_post_trade/Ni_750400",
            ),
            ("trade2",),
        ),
        TransitionSpec("trade3", "S5", "S6", "S7", ("3rd_post_trade/Ni_283324",), ("trade3",)),
    ),
    "Co": (
        TransitionSpec("trade1", "S1", "S2", "S3", ("1st_post_trade/Co_260500",), ("trade1",)),
        TransitionSpec(
            "trade2",
            "S3",
            "S4",
            "S5",
            ("2nd_post_trade/Co_282200", "2nd_post_trade/Co_810520", "2nd_post_trade/Co_810530"),
            ("trade2",),
        ),
        TransitionSpec("trade3", "S5", "S6", "S7", ("3rd_post_trade/Co_283329",), ("trade3",)),
    ),
}


HYPERPARAM_GRID = (
    HyperParameters(1.00, 0.00, 99.0, 0.00, 0, 1.00, 1.00, 1.00, 1, 0.00, 0.00, 0.00),
    HyperParameters(0.60, 0.00, 1.05, 0.00, 5, 0.80, 1.20, 0.10, 2, 0.10, 0.03, 0.02),
    HyperParameters(0.60, 0.10, 1.05, 0.35, 5, 0.80, 1.20, 0.10, 2, 0.10, 0.03, 0.02),
    HyperParameters(0.75, 0.00, 1.10, 0.00, 5, 0.75, 1.25, 0.10, 2, 0.12, 0.03, 0.02),
    HyperParameters(0.75, 0.10, 1.10, 0.35, 5, 0.75, 1.25, 0.10, 2, 0.12, 0.03, 0.02),
    HyperParameters(0.90, 0.00, 1.15, 0.00, 6, 0.75, 1.25, 0.10, 2, 0.15, 0.03, 0.02),
    HyperParameters(0.90, 0.10, 1.15, 0.35, 6, 0.75, 1.25, 0.10, 2, 0.15, 0.03, 0.02),
)
@lru_cache(maxsize=1)
def _modules() -> dict[str, dict[str, Any]]:
    return {
        "Li": {
            "data": importlib.import_module("trade_flow.legacy_site.services.lithium_data"),
            "sankey": importlib.import_module("trade_flow.legacy_site.services.lithium_sankey"),
        },
        "Ni": {
            "data": importlib.import_module("trade_flow.legacy_site.services.nickel_data"),
            "sankey": importlib.import_module("trade_flow.legacy_site.services.nickel_sankey"),
        },
        "Co": {
            "data": importlib.import_module("trade_flow.legacy_site.services.cobalt_data"),
            "sankey": importlib.import_module("trade_flow.legacy_site.services.cobalt_sankey"),
        },
    }


def _bundle(metal: str) -> dict[str, Any]:
    if metal not in METALS:
        raise ValueError(f"Unsupported metal: {metal}")
    return _modules()[metal]


def _edge_map_to_trade_flows(metal: str, edge_map: EdgeMap):
    trade_flow_type = _trade_flow_type(metal)
    rows = []
    for (exporter, importer), value in sorted(edge_map.items()):
        if value <= EPSILON:
            continue
        rows.append(trade_flow_type(exporter=int(exporter), importer=int(importer), value=float(value)))
    return tuple(rows)


def _override_original_inputs(metal: str, year: int, inputs):
    if metal != "Ni":
        return inputs
    # The current baseline should reflect all Ni 2nd-post-trade Comtrade folders,
    # not only the simplified 2.1 single-folder nickel trade2 input.
    ni_trade2_folders = TRANSITIONS_BY_METAL["Ni"][1].folder_names
    merged_trade2 = _merge_edge_maps(*(load_trade_folder(folder_name, year, "import") for folder_name in ni_trade2_folders))
    return replace(inputs, trade2=_edge_map_to_trade_flows(metal, merged_trade2))


def load_year_inputs(metal: str, year: int):
    inputs = _bundle(metal)["data"].load_year_inputs(year)
    return _override_original_inputs(metal, year, inputs)


def build_country_graph(metal: str, year: int, *, inputs=None, cobalt_mode: str = DEFAULT_COBALT_MODE):
    bundle = _bundle(metal)
    sankey = bundle["sankey"]
    resolved_inputs = inputs or load_year_inputs(metal, year)
    if metal == "Co":
        return sankey._build_country_payload(resolved_inputs, cobalt_mode)
    return sankey._build_country_payload(resolved_inputs)


def build_country_payload(metal: str, year: int, *, cobalt_mode: str = DEFAULT_COBALT_MODE) -> dict[str, Any]:
    bundle = _bundle(metal)
    sankey = bundle["sankey"]
    if metal == "Co":
        return sankey.build_app_payload(year, "country", cobalt_mode=cobalt_mode)
    return sankey.build_app_payload(year, "country")


def serialize_inputs(inputs) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(inputs)))


def _trade_flow_type(metal: str):
    return _bundle(metal)["data"].TradeFlow


def replace_trade_fields(metal: str, base_inputs, field_flow_maps: dict[str, dict[tuple[int, int], float]]):
    trade_flow_type = _trade_flow_type(metal)
    replacements: dict[str, Any] = {}
    for field_name, edge_map in field_flow_maps.items():
        rows = []
        for (exporter, importer), value in sorted(edge_map.items()):
            if value <= EPSILON:
                continue
            rows.append(trade_flow_type(exporter=int(exporter), importer=int(importer), value=float(value)))
        replacements[field_name] = tuple(rows)
    return replace(base_inputs, **replacements)


def _sum_maps(*mappings: dict[int, float]) -> dict[int, float]:
    result: dict[int, float] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            result[int(key)] = result.get(int(key), 0.0) + float(value)
    return {key: value for key, value in result.items() if abs(value) > EPSILON}


def transition_contexts(metal: str, inputs, *, cobalt_mode: str = DEFAULT_COBALT_MODE) -> dict[str, TransitionContext]:
    sankey = _bundle(metal)["sankey"]
    contexts: dict[str, TransitionContext] = {}
    if metal == "Li":
        contexts["trade1"] = TransitionContext(
            "trade1", "S1", "S2", "S3", dict(inputs.mining_total), dict(inputs.mining_total), {},
            dict(sankey._first_post_trade_balance(inputs)),
            dict(inputs.processing_total), TRANSITIONS_BY_METAL["Li"][0].folder_names, TRANSITIONS_BY_METAL["Li"][0].input_fields,
        )
        contexts["trade2"] = TransitionContext(
            "trade2", "S3", "S4", "S5", dict(inputs.processing_total), dict(inputs.processing_battery), {},
            dict(sankey._second_post_trade_balance(inputs)),
            dict(inputs.refining_total), TRANSITIONS_BY_METAL["Li"][1].folder_names, TRANSITIONS_BY_METAL["Li"][1].input_fields,
        )
        contexts["trade3"] = TransitionContext(
            "trade3", "S5", "S6", "S7", dict(inputs.refining_total), dict(inputs.refining_total), {},
            _sum_maps(inputs.cathode_ncm_nca_balance, inputs.cathode_lfp_balance),
            dict(inputs.cathode_total), TRANSITIONS_BY_METAL["Li"][2].folder_names, TRANSITIONS_BY_METAL["Li"][2].input_fields,
        )
        return contexts
    if metal == "Ni":
        contexts["trade1"] = TransitionContext(
            "trade1", "S1", "S2", "S3", dict(inputs.mining_total), dict(inputs.mining_concentrate), dict(sankey._processing_direct_local(inputs)),
            dict(inputs.processing_balance), dict(inputs.processing_total), TRANSITIONS_BY_METAL["Ni"][0].folder_names, TRANSITIONS_BY_METAL["Ni"][0].input_fields,
        )
        contexts["trade2"] = TransitionContext(
            "trade2", "S3", "S4", "S5", dict(inputs.processing_total), dict(inputs.processing_battery), {},
            dict(inputs.refining_balance), dict(inputs.refining_total), TRANSITIONS_BY_METAL["Ni"][1].folder_names, TRANSITIONS_BY_METAL["Ni"][1].input_fields,
        )
        contexts["trade3"] = TransitionContext(
            "trade3", "S5", "S6", "S7", dict(inputs.refining_total), dict(inputs.refining_total), {},
            dict(inputs.cathode_balance), dict(inputs.cathode_total), TRANSITIONS_BY_METAL["Ni"][2].folder_names, TRANSITIONS_BY_METAL["Ni"][2].input_fields,
        )
        return contexts
    refining_total, refining_balance, cathode_total_balance, _chem_balance = sankey._refining_maps_for_mode(inputs, cobalt_mode)
    contexts["trade1"] = TransitionContext(
        "trade1", "S1", "S2", "S3", dict(inputs.mining_total), dict(inputs.mining_concentrate), dict(sankey._first_post_trade_direct_local(inputs)),
        {}, dict(sankey._first_post_trade_totals(inputs)), TRANSITIONS_BY_METAL["Co"][0].folder_names, TRANSITIONS_BY_METAL["Co"][0].input_fields,
    )
    contexts["trade2"] = TransitionContext(
        "trade2", "S3", "S4", "S5", dict(inputs.processing_total), dict(inputs.processing_total), dict(sankey._second_post_trade_direct_local(inputs)),
        dict(refining_balance), dict(refining_total), TRANSITIONS_BY_METAL["Co"][1].folder_names, TRANSITIONS_BY_METAL["Co"][1].input_fields,
    )
    contexts["trade3"] = TransitionContext(
        "trade3", "S5", "S6", "S7", dict(refining_total), dict(refining_total), {},
        dict(cathode_total_balance), dict(inputs.cathode_total), TRANSITIONS_BY_METAL["Co"][2].folder_names, TRANSITIONS_BY_METAL["Co"][2].input_fields,
    )
    return contexts


def node_value_map(nodes: dict[str, Any], links: list[Any]) -> dict[str, float]:
    incoming: dict[str, float] = defaultdict(float)
    outgoing: dict[str, float] = defaultdict(float)
    for link in links:
        outgoing[link.source] += float(link.value)
        incoming[link.target] += float(link.value)
    return {key: max(incoming.get(key, 0.0), outgoing.get(key, 0.0)) for key in nodes}


def node_records(nodes: dict[str, Any], links: list[Any], metal: str, year: int, scenario: str) -> list[dict[str, Any]]:
    values = node_value_map(nodes, links)
    rows = []
    for key, spec in nodes.items():
        rows.append(
            {
                "metal": metal,
                "year": year,
                "scenario": scenario,
                "key": key,
                "stage": spec.stage,
                "label": spec.label,
                "kind": spec.kind,
                "region": spec.region,
                "value": float(values.get(key, 0.0)),
                "is_unknown": int("Unknown" in spec.label),
                "is_non_source": int(spec.label.startswith("From Non-")),
                "is_non_target": int(" to Non-" in spec.label or spec.label.endswith("Non-Cathode")),
                "is_structural_sink": int(spec.label in {"Processing Unrelated", "Refining Other Products"}),
            }
        )
    return rows


def link_records(nodes: dict[str, Any], links: list[Any], metal: str, year: int, scenario: str) -> list[dict[str, Any]]:
    rows = []
    for link in links:
        rows.append(
            {
                "metal": metal,
                "year": year,
                "scenario": scenario,
                "source": link.source,
                "source_stage": nodes[link.source].stage,
                "source_label": nodes[link.source].label,
                "target": link.target,
                "target_stage": nodes[link.target].stage,
                "target_label": nodes[link.target].label,
                "value": float(link.value),
            }
        )
    return rows


def summarize_graph(nodes: dict[str, Any], links: list[Any], metal: str, year: int, scenario: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_df = pd.DataFrame(node_records(nodes, links, metal, year, scenario))
    summary_row = {
        "metal": metal,
        "year": year,
        "scenario": scenario,
        "unknown_total": float(node_df.loc[node_df["is_unknown"] == 1, "value"].sum()),
        "non_source_total": float(node_df.loc[node_df["is_non_source"] == 1, "value"].sum()),
        "non_target_total": float(node_df.loc[node_df["is_non_target"] == 1, "value"].sum()),
        "structural_sink_total": float(node_df.loc[node_df["is_structural_sink"] == 1, "value"].sum()),
        "total_special": float(node_df.loc[node_df["kind"] != "regular", "value"].sum()),
        "total_regular": float(node_df.loc[node_df["kind"] == "regular", "value"].sum()),
    }
    return node_df, pd.DataFrame([summary_row])


def stage_summary(node_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (metal, year, scenario, stage), group in node_df.groupby(["metal", "year", "scenario", "stage"]):
        rows.append(
            {
                "metal": metal,
                "year": year,
                "scenario": scenario,
                "stage": stage,
                "total_value": float(group["value"].sum()),
                "unknown_total": float(group.loc[group["is_unknown"] == 1, "value"].sum()),
                "special_total": float(group.loc[group["kind"] != "regular", "value"].sum()),
            }
        )
    return pd.DataFrame(rows)


# Trade loading / 贸易读取与镜像融合
EdgeMap = dict[tuple[int, int], float]


def _merge_edge_maps(*maps: EdgeMap) -> EdgeMap:
    merged: EdgeMap = {}
    for edge_map in maps:
        for edge, value in edge_map.items():
            merged[edge] = merged.get(edge, 0.0) + float(value)
    return {edge: value for edge, value in merged.items() if value > EPSILON}


def _country_outgoing(edge_map: EdgeMap) -> dict[int, float]:
    totals: dict[int, float] = defaultdict(float)
    for (exporter, _importer), value in edge_map.items():
        totals[exporter] += float(value)
    return dict(totals)


def _country_incoming(edge_map: EdgeMap) -> dict[int, float]:
    totals: dict[int, float] = defaultdict(float)
    for (_exporter, importer), value in edge_map.items():
        totals[importer] += float(value)
    return dict(totals)


def _scale_country_map(base_map: dict[int, float], share_map: dict[int, float]) -> dict[int, float]:
    # Keep optimization at the HS-code level.
    # 这里把 stage total 近似分摊到单个 HS code，避免多个 code 先合并再统一调。
    scaled: dict[int, float] = {}
    for country_id, value in base_map.items():
        scaled_value = float(value) * float(share_map.get(country_id, 0.0))
        if abs(scaled_value) > EPSILON:
            scaled[int(country_id)] = scaled_value
    return scaled


def _folder_context(context: TransitionContext, folder_map: EdgeMap, group_map: EdgeMap) -> TransitionContext:
    group_outgoing = _country_outgoing(group_map)
    folder_outgoing = _country_outgoing(folder_map)
    exporter_share = {
        country_id: (
            float(folder_outgoing.get(country_id, 0.0)) / float(group_outgoing.get(country_id, 0.0))
            if float(group_outgoing.get(country_id, 0.0)) > EPSILON
            else 0.0
        )
        for country_id in set(group_outgoing) | set(folder_outgoing) | set(context.trade_supply) | set(context.source_totals)
    }

    group_incoming = _country_incoming(group_map)
    folder_incoming = _country_incoming(folder_map)
    importer_share = {
        country_id: (
            float(folder_incoming.get(country_id, 0.0)) / float(group_incoming.get(country_id, 0.0))
            if float(group_incoming.get(country_id, 0.0)) > EPSILON
            else 0.0
        )
        for country_id in set(group_incoming) | set(folder_incoming) | set(context.target_totals) | set(context.balance_map) | set(context.direct_local)
    }

    return TransitionContext(
        key=context.key,
        source_stage=context.source_stage,
        post_stage=context.post_stage,
        target_stage=context.target_stage,
        source_totals=_scale_country_map(context.source_totals, exporter_share),
        trade_supply=_scale_country_map(context.trade_supply, exporter_share),
        direct_local=_scale_country_map(context.direct_local, importer_share),
        balance_map=_scale_country_map(context.balance_map, importer_share),
        target_totals=_scale_country_map(context.target_totals, importer_share),
        folder_names=context.folder_names,
        input_fields=context.input_fields,
    )


def load_trade_folder(folder_name: str, year: int, trade_mode: str) -> EdgeMap:
    folder = TRADE_ROOT / trade_mode / folder_name
    flows: EdgeMap = defaultdict(float)
    if not folder.exists():
        return {}
    for path in sorted(folder.glob("*_combined.csv")):
        try:
            reporter_id = int(path.name.split("_")[0])
        except ValueError:
            continue
        if reporter_id == 0:
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    row_year = int(row["Year"])
                    partner_id = int(float(row["Partner ID"]))
                    quantity = float(row["Quantity"])
                except (TypeError, ValueError, KeyError):
                    continue
                if row_year != year or partner_id == 0 or quantity <= EPSILON:
                    continue
                if trade_mode == "import":
                    edge = (partner_id, reporter_id)
                else:
                    edge = (reporter_id, partner_id)
                flows[edge] += quantity
    return dict(flows)


def smooth_folder(folder_name: str, year: int, trade_mode: str, lag_weight: float) -> EdgeMap:
    current = load_trade_folder(folder_name, year, trade_mode)
    if lag_weight <= EPSILON:
        return current
    weights = {year: 1.0}
    if year - 1 in YEARS:
        weights[year - 1] = lag_weight
    if year + 1 in YEARS:
        weights[year + 1] = lag_weight
    total_weight = sum(weights.values())
    smoothed: EdgeMap = defaultdict(float)
    for candidate_year, weight in weights.items():
        edge_map = load_trade_folder(folder_name, candidate_year, trade_mode)
        for edge, value in edge_map.items():
            smoothed[edge] += value * weight / total_weight
    return dict(smoothed)


def reconcile_group(folder_names: tuple[str, ...], year: int, mirror_weight: float, lag_weight: float) -> tuple[dict[str, EdgeMap], EdgeMap]:
    reconciled_fields: dict[str, EdgeMap] = {}
    for folder_name in folder_names:
        import_map = smooth_folder(folder_name, year, "import", lag_weight)
        export_map = smooth_folder(folder_name, year, "export", lag_weight)
        edges = set(import_map) | set(export_map)
        reconciled_fields[folder_name] = {
            edge: mirror_weight * import_map.get(edge, 0.0) + (1.0 - mirror_weight) * export_map.get(edge, 0.0)
            for edge in edges
            if mirror_weight * import_map.get(edge, 0.0) + (1.0 - mirror_weight) * export_map.get(edge, 0.0) > EPSILON
        }
    return reconciled_fields, _merge_edge_maps(*reconciled_fields.values())


def apply_reexport(flow_map: EdgeMap, supply_map: dict[int, float], direct_local: dict[int, float], hub_threshold: float, reexport_cap: float) -> EdgeMap:
    if reexport_cap <= EPSILON:
        return dict(flow_map)
    adjusted = dict(flow_map)
    outgoing: dict[int, float] = defaultdict(float)
    incoming: dict[int, float] = defaultdict(float)
    incoming_edges: dict[int, dict[tuple[int, int], float]] = defaultdict(dict)
    outgoing_edges: dict[int, dict[tuple[int, int], float]] = defaultdict(dict)
    for (exporter, importer), value in flow_map.items():
        outgoing[exporter] += value
        incoming[importer] += value
        incoming_edges[importer][(exporter, importer)] = value
        outgoing_edges[exporter][(exporter, importer)] = value
    for hub_id in sorted(outgoing, key=lambda country_id: outgoing[country_id], reverse=True):
        total_export = outgoing.get(hub_id, 0.0)
        if total_export <= EPSILON:
            continue
        local_cap = float(supply_map.get(hub_id, 0.0)) + float(direct_local.get(hub_id, 0.0))
        if total_export <= max(local_cap * hub_threshold, EPSILON):
            continue
        total_import = incoming.get(hub_id, 0.0)
        if total_import <= EPSILON:
            continue
        reexport_total = min(total_export - local_cap, total_import, total_export * reexport_cap)
        if reexport_total <= EPSILON:
            continue
        reexport_share = reexport_total / total_export
        import_weights = {edge[0]: value / total_import for edge, value in incoming_edges.get(hub_id, {}).items() if value > EPSILON}
        for edge, edge_value in list(outgoing_edges.get(hub_id, {}).items()):
            exporter, importer = edge
            moved = edge_value * reexport_share
            kept = edge_value - moved
            if kept <= EPSILON:
                adjusted.pop(edge, None)
            else:
                adjusted[edge] = kept
            for origin, share in import_weights.items():
                reassigned_value = moved * share
                if reassigned_value > EPSILON:
                    adjusted[(origin, importer)] = adjusted.get((origin, importer), 0.0) + reassigned_value
    return {edge: value for edge, value in adjusted.items() if value > EPSILON}


def split_group_map(final_group_map: EdgeMap, field_maps: dict[str, EdgeMap]) -> dict[str, EdgeMap]:
    field_totals = {field_name: sum(edge_map.values()) for field_name, edge_map in field_maps.items()}
    total_value = sum(field_totals.values())
    fallback = {
        field_name: (field_total / total_value if total_value > EPSILON else 1.0 / max(len(field_maps), 1))
        for field_name, field_total in field_totals.items()
    }
    split_maps: dict[str, EdgeMap] = {field_name: {} for field_name in field_maps}
    per_edge_total = _merge_edge_maps(*field_maps.values())
    for edge, final_value in final_group_map.items():
        base_total = per_edge_total.get(edge, 0.0)
        if base_total > EPSILON:
            shares = {field_name: field_maps[field_name].get(edge, 0.0) / base_total for field_name in field_maps}
        else:
            shares = fallback
        for field_name, share in shares.items():
            allocated = final_value * share
            if allocated > EPSILON:
                split_maps[field_name][edge] = allocated
    return split_maps


# Transition objective / 这里复刻 shared_sankey 的 country residual 口径

def _resolve_balance(balance_value: float, known_external_incoming: float, known_exports: float) -> tuple[float, float]:
    net_external_requirement = float(balance_value) + float(known_exports) - float(known_external_incoming)
    return max(net_external_requirement, 0.0), max(-net_external_requirement, 0.0)


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
    for country_id, target_total in context.target_totals.items():
        trade_need = max(target_total - context.direct_local.get(country_id, 0.0), 0.0)
        balance_value = context.balance_map.get(country_id, trade_need - context.trade_supply.get(country_id, 0.0))
        gap, excess = _resolve_balance(balance_value, external_incoming.get(country_id, 0.0), known_exports.get(country_id, 0.0))
        unknown_total += gap + excess

    return {
        "unknown_total": unknown_total,
        "non_source_total": float(sum(non_source_imports.values())),
        "non_target_total": float(sum(exporter_non_target.values())),
    }


def _candidate_exporters(flow_map: EdgeMap, context: TransitionContext, max_count: int) -> list[int]:
    outgoing: dict[int, float] = defaultdict(float)
    for (exporter, _importer), value in flow_map.items():
        outgoing[exporter] += value
    scored: list[tuple[float, int]] = []
    for exporter, outflow in outgoing.items():
        if exporter not in context.source_totals:
            continue
        capacity = max(float(context.trade_supply.get(exporter, 0.0)), EPSILON)
        mismatch = abs(outflow - capacity) / capacity
        scored.append((outflow * (1.0 + mismatch), exporter))
    scored.sort(reverse=True)
    return [exporter for _score, exporter in scored[:max_count]]


def _apply_exporter_scales(flow_map: EdgeMap, multipliers: dict[int, float]) -> EdgeMap:
    return {edge: value * multipliers.get(edge[0], 1.0) for edge, value in flow_map.items() if value * multipliers.get(edge[0], 1.0) > EPSILON}


def _objective(metrics: dict[str, float], multipliers: dict[int, float], params: HyperParameters) -> float:
    return (
        metrics["unknown_total"]
        + params.non_source_weight * metrics["non_source_total"]
        + params.non_target_weight * metrics["non_target_total"]
        + params.deviation_weight * sum(abs(value - 1.0) for value in multipliers.values())
    )


def optimize_transition(flow_map: EdgeMap, context: TransitionContext, params: HyperParameters) -> tuple[EdgeMap, dict[int, float], dict[str, float]]:
    if not flow_map:
        return {}, {}, evaluate_transition({}, context)
    candidates = _candidate_exporters(flow_map, context, params.priority_country_count)
    multipliers = {country_id: 1.0 for country_id in candidates}
    best_map = dict(flow_map)
    best_metrics = evaluate_transition(best_map, context)
    best_score = _objective(best_metrics, multipliers, params)
    for _ in range(params.scale_passes):
        for exporter in candidates:
            local_scale = multipliers[exporter]
            local_map = best_map
            local_metrics = best_metrics
            local_score = best_score
            for scale in params.scale_values():
                trial = dict(multipliers)
                trial[exporter] = scale
                trial_map = _apply_exporter_scales(flow_map, trial)
                trial_metrics = evaluate_transition(trial_map, context)
                trial_score = _objective(trial_metrics, trial, params)
                if trial_score + 1e-9 < local_score:
                    local_scale = scale
                    local_map = trial_map
                    local_metrics = trial_metrics
                    local_score = trial_score
            multipliers[exporter] = local_scale
            best_map = local_map
            best_metrics = local_metrics
            best_score = local_score
    return best_map, multipliers, best_metrics


def optimize_inputs(metal: str, year: int, base_inputs, params: HyperParameters, *, cobalt_mode: str = DEFAULT_COBALT_MODE):
    contexts = transition_contexts(metal, base_inputs, cobalt_mode=cobalt_mode)
    replacement_field_maps: dict[str, EdgeMap] = {}
    transition_rows: list[dict[str, Any]] = []
    for transition_key, context in contexts.items():
        field_maps, group_map = reconcile_group(context.folder_names, year, params.mirror_weight, params.lag_weight)
        optimized_folder_maps: dict[str, EdgeMap] = {}
        for folder_name, folder_map in field_maps.items():
            # Optimize each HS code separately, then merge only when mapping back to 2.1 input fields.
            # 每个 HS code 单独做优化，最后仅为了回填 2.1 输入字段才做合并。
            hs_context = _folder_context(context, folder_map, group_map)
            hs_map = apply_reexport(folder_map, hs_context.trade_supply, hs_context.direct_local, params.hub_threshold, params.reexport_cap)
            optimized_hs_map, multipliers, stage_metrics = optimize_transition(hs_map, hs_context, params)
            optimized_folder_maps[folder_name] = optimized_hs_map
            transition_rows.append(
                {
                    "metal": metal,
                    "year": year,
                    "transition": transition_key,
                    "folder_name": folder_name,
                    "stage_unknown_total": stage_metrics["unknown_total"],
                    "non_source_total": stage_metrics["non_source_total"],
                    "non_target_total": stage_metrics["non_target_total"],
                    "multipliers_json": json.dumps(multipliers, ensure_ascii=False),
                    "params_json": json.dumps(asdict(params), ensure_ascii=False),
                }
            )
        if len(context.input_fields) == 1:
            replacement_field_maps[context.input_fields[0]] = _merge_edge_maps(*optimized_folder_maps.values())
        else:
            for field_name, folder_name in zip(context.input_fields, context.folder_names):
                replacement_field_maps[field_name] = optimized_folder_maps.get(folder_name, {})
    return replace_trade_fields(metal, base_inputs, replacement_field_maps), pd.DataFrame(transition_rows)


def _ensure_output_dirs() -> None:
    for path in (BASELINE_OUTPUT_ROOT, OPTIMIZED_OUTPUT_ROOT, COMPARISON_OUTPUT_ROOT, SPREADSHEET_OUTPUT_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def _write_case_mode_csvs(
    case_dir: Path,
    metal: str,
    year: int,
    scenario: str,
    mode_suffix: str,
    nodes,
    links,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    node_df = pd.DataFrame(node_records(nodes, links, metal, year, scenario))
    link_df = pd.DataFrame(link_records(nodes, links, metal, year, scenario))
    summary_df = summarize_graph(nodes, links, metal, year, scenario)[1]
    suffix = f"_{mode_suffix}" if mode_suffix else ""
    node_df.to_csv(case_dir / f"{scenario}_nodes{suffix}.csv", index=False)
    link_df.to_csv(case_dir / f"{scenario}_links{suffix}.csv", index=False)
    summary_df.to_csv(case_dir / f"{scenario}_summary{suffix}.csv", index=False)
    return node_df, link_df, summary_df


def _write_case_exports(root: Path, metal: str, year: int, scenario: str, inputs, nodes, links, extra_payload: dict[str, Any] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    case_dir = root / metal / str(year)
    case_dir.mkdir(parents=True, exist_ok=True)
    with (case_dir / f"{scenario}_inputs.json").open("w", encoding="utf-8") as handle:
        json.dump(serialize_inputs(inputs), handle, ensure_ascii=False, indent=2)
    if extra_payload is not None:
        with (case_dir / f"{scenario}_payload.json").open("w", encoding="utf-8") as handle:
            json.dump(extra_payload, handle, ensure_ascii=False, indent=2)
    node_df, link_df, summary_df = _write_case_mode_csvs(case_dir, metal, year, scenario, "", nodes, links)
    if metal == "Co":
        # Precompute all cobalt refining scenarios so the website can read frozen CSV snapshots
        # directly instead of rebuilding max/min/middle views on the fly.
        cobalt_modes = ("mid", "max", "min")
        for cobalt_mode in cobalt_modes:
            if cobalt_mode == DEFAULT_COBALT_MODE:
                _write_case_mode_csvs(case_dir, metal, year, scenario, cobalt_mode, nodes, links)
                continue
            mode_nodes, mode_links = build_country_graph(metal, year, inputs=inputs, cobalt_mode=cobalt_mode)
            _write_case_mode_csvs(case_dir, metal, year, scenario, cobalt_mode, mode_nodes, mode_links)
    return node_df, link_df, summary_df


def export_baseline() -> tuple[pd.DataFrame, pd.DataFrame]:
    all_summary = []
    all_stage = []
    for metal in METALS:
        for year in YEARS:
            inputs = load_year_inputs(metal, year)
            payload = build_country_payload(metal, year, cobalt_mode=DEFAULT_COBALT_MODE)
            nodes, links = build_country_graph(metal, year, inputs=inputs, cobalt_mode=DEFAULT_COBALT_MODE)
            node_df, _link_df, summary_df = _write_case_exports(BASELINE_OUTPUT_ROOT, metal, year, "baseline", inputs, nodes, links, payload)
            all_summary.append(summary_df)
            all_stage.append(stage_summary(node_df))
    baseline_summary = pd.concat(all_summary, ignore_index=True)
    baseline_stage = pd.concat(all_stage, ignore_index=True)
    baseline_summary.to_csv(COMPARISON_OUTPUT_ROOT / "baseline_summary.csv", index=False)
    baseline_stage.to_csv(COMPARISON_OUTPUT_ROOT / "baseline_stage_summary.csv", index=False)
    return baseline_summary, baseline_stage


def run_search_by_metal() -> tuple[dict[str, HyperParameters], pd.DataFrame]:
    best_params_by_metal: dict[str, HyperParameters] = {}
    search_frames = []
    for metal in METALS:
        rows = []
        best_params: HyperParameters | None = None
        best_score: float | None = None
        for params in HYPERPARAM_GRID:
            total_unknown = 0.0
            total_special = 0.0
            for year in YEARS:
                base_inputs = load_year_inputs(metal, year)
                optimized_inputs, _detail = optimize_inputs(metal, year, base_inputs, params, cobalt_mode=DEFAULT_COBALT_MODE)
                nodes, links = build_country_graph(metal, year, inputs=optimized_inputs, cobalt_mode=DEFAULT_COBALT_MODE)
                _node_df, summary_df = summarize_graph(nodes, links, metal, year, "optimized")
                total_unknown += float(summary_df.iloc[0]["unknown_total"])
                total_special += float(summary_df.iloc[0]["total_special"])
            score = total_unknown + 0.02 * total_special
            row = {"metal": metal, **asdict(params), "score": score, "unknown_total": total_unknown, "total_special": total_special}
            rows.append(row)
            if best_score is None or score < best_score:
                best_score = score
                best_params = params
        if best_params is None:
            raise RuntimeError(f"No hyperparameter result was produced for {metal}.")
        metal_df = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
        metal_df["rank_within_metal"] = range(1, len(metal_df) + 1)
        search_frames.append(metal_df)
        best_params_by_metal[metal] = best_params
    search_df = pd.concat(search_frames, ignore_index=True)
    search_df.to_csv(COMPARISON_OUTPUT_ROOT / "hyperparameter_search.csv", index=False)
    return best_params_by_metal, search_df


def export_optimized(best_params_by_metal: dict[str, HyperParameters]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_summary = []
    all_stage = []
    all_transition = []
    for metal in METALS:
        params = best_params_by_metal[metal]
        for year in YEARS:
            base_inputs = load_year_inputs(metal, year)
            optimized_inputs, transition_df = optimize_inputs(metal, year, base_inputs, params, cobalt_mode=DEFAULT_COBALT_MODE)
            nodes, links = build_country_graph(metal, year, inputs=optimized_inputs, cobalt_mode=DEFAULT_COBALT_MODE)
            node_df, _link_df, summary_df = _write_case_exports(
                OPTIMIZED_OUTPUT_ROOT,
                metal,
                year,
                "optimized",
                optimized_inputs,
                nodes,
                links,
                {"best_params": asdict(params), "metal": metal},
            )
            all_summary.append(summary_df)
            all_stage.append(stage_summary(node_df))
            all_transition.append(transition_df)
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
    best_params_by_metal: dict[str, HyperParameters],
) -> pd.DataFrame:
    comparison = baseline_summary.merge(optimized_summary, on=["metal", "year"], suffixes=("_baseline", "_optimized"))
    comparison["unknown_reduction"] = comparison["unknown_total_baseline"] - comparison["unknown_total_optimized"]
    comparison["unknown_reduction_pct"] = comparison["unknown_reduction"] / comparison["unknown_total_baseline"].replace(0, pd.NA)
    comparison["special_reduction"] = comparison["total_special_baseline"] - comparison["total_special_optimized"]
    comparison.to_csv(COMPARISON_OUTPUT_ROOT / "comparison_summary.csv", index=False)
    best_params_df = pd.DataFrame(
        [{"metal": metal, **asdict(params)} for metal, params in best_params_by_metal.items()]
    )
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


def main() -> None:
    _ensure_output_dirs()
    baseline_summary, baseline_stage = export_baseline()
    best_params_by_metal, search_df = run_search_by_metal()
    optimized_summary, optimized_stage, transition_detail = export_optimized(best_params_by_metal)
    comparison = build_comparison_workbook(
        baseline_summary,
        optimized_summary,
        baseline_stage,
        optimized_stage,
        search_df,
        transition_detail,
        best_params_by_metal,
    )
    by_metal = {}
    for metal, params in best_params_by_metal.items():
        metal_slice = comparison.loc[comparison["metal"] == metal]
        by_metal[metal] = {
            "best_params": asdict(params),
            "total_unknown_reduction": float(metal_slice["unknown_reduction"].sum()),
            "cases_improved": int((metal_slice["unknown_reduction"] > 0).sum()),
            "case_count": int(len(metal_slice)),
        }
    result = {
        "best_params_by_metal": by_metal,
        "mean_unknown_reduction": float(comparison["unknown_reduction"].mean()),
        "median_unknown_reduction": float(comparison["unknown_reduction"].median()),
        "cases_improved": int((comparison["unknown_reduction"] > 0).sum()),
        "case_count": int(len(comparison)),
    }
    with (COMPARISON_OUTPUT_ROOT / "feasibility_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


