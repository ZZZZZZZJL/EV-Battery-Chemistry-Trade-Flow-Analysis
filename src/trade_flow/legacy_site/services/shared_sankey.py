from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go


VIEW_MODES = ["country", "chemistry", "chemistry_only"]
VIEW_LABELS = {
    "country": "By Country",
    "chemistry": "By Country & Chemistry",
    "chemistry_only": "By Chemistry Type",
}
SORT_MODES = ["size", "manual", "continent"]
DEFAULT_SORT_MODE = "size"
THEME_MODES = ("dark", "light")
DEFAULT_THEME = "dark"
SPECIAL_NODE_POSITIONS = ("first", "last")
DEFAULT_SPECIAL_POSITION = "first"
DEFAULT_REFERENCE_QTY = 60000.0
STAGE_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
STAGE_LABELS = {
    "S1": "S1 Mining",
    "S2": "S2 1st Post Trade",
    "S3": "S3 Processing",
    "S4": "S4 2nd Post Trade",
    "S5": "S5 Refining",
    "S6": "S6 3rd Post Trade",
    "S7": "S7 Cathode",
}
STAGE_NAMES = {
    "S1": "Mining",
    "S2": "1st&nbsp;Post<br>Trade",
    "S3": "Processing",
    "S4": "2nd&nbsp;Post<br>Trade",
    "S5": "Refining",
    "S6": "3rd&nbsp;Post<br>Trade",
    "S7": "Cathode",
}
X_MAP = {
    "S1": 0.06,
    "S2": 0.20,
    "S3": 0.34,
    "S4": 0.48,
    "S5": 0.62,
    "S6": 0.76,
    "S7": 0.90,
}
SPECIAL_COLORS = {
    "non_source": "#8b929a",
    "unknown_source": "#8b929a",
    "non_target": "#8b929a",
    "unknown_target": "#8b929a",
    "processing_unrelated": "#8b929a",
    "aggregate": "#8e725a",
    "reference": "#8b929a",
    "refining_other": "#8fa5b8",
    "ncm": "#1d4ed8",
    "nmc": "#1d4ed8",
    "nca": "#7c3aed",
    "lfp": "#16a34a",
}
REGION_COLORS = {
    "Africa": "#800080",
    "Europe": "#008000",
    "Asia": "#FFA500",
    "North America": "#b38f00",
    "South America": "#FF0000",
    "Oceania": "#0000FF",
    "Antarctica": "#000000",
    "Unknown": "#7f8c8d",
}
REGION_ORDER = ["Africa", "Asia", "Europe", "North America", "South America", "Oceania", "Antarctica", "Unknown"]
PADDING_PX = 52.0
GAP_PX = 22.0
PLOTLY_NODE_PAD_PX = 32.0
MIN_STAGE_HEIGHT_PX = 100.0
REFERENCE_NODE_HEIGHT_PX = 80.0
REFERENCE_NODE_CENTER_X = 0.94
REFERENCE_NODE_HALF_WIDTH_PAPER = 0.008
REFERENCE_LABEL_GAP_PAPER = 0.012
TOP_BAND_PX = 80.0
BOTTOM_BAND_PX = 80.0
STAGE_TITLE_Y_RATIO = 0.30
TITLE_TEXT_BY_THEME = {
    "dark": "#f8f4eb",
    "light": "#20160e",
}
BODY_TEXT_BY_THEME = {
    "dark": "#f5efe2",
    "light": "#32251c",
}
REFERENCE_TEXT_BY_THEME = {
    "dark": "#1a140f",
    "light": "#1a140f",
}
BODY_FONT_FAMILY = "Aptos, Segoe UI, sans-serif"
DISPLAY_FONT_FAMILY = "Georgia, Times New Roman, serif"


@dataclass(frozen=True)
class NodeSpec:
    key: str
    stage: str
    label: str
    color: str
    kind: str
    hover: str
    region: str


@dataclass(frozen=True)
class LinkSpec:
    source: str
    target: str
    value: float
    color: str


def view_mode_label(view_mode: str) -> str:
    return VIEW_LABELS.get(view_mode, view_mode)


def resolve_view_mode(view_mode: str) -> str:
    normalized = str(view_mode).strip().lower().replace("-", "_")
    if normalized not in VIEW_MODES:
        raise ValueError(f"Unsupported view mode: {view_mode}")
    return normalized


def _hex_to_rgba(hex_value: str, opacity: float = 0.34) -> str:
    color = hex_value.lstrip("#")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


def _clip(mapping: dict[int, float], epsilon: float) -> dict[int, float]:
    return {
        int(key): float(value)
        for key, value in mapping.items()
        if abs(float(value)) > epsilon
    }


def _sum_maps(*mappings: dict[int, float]) -> dict[int, float]:
    result: dict[int, float] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            result[int(key)] = result.get(int(key), 0.0) + float(value)
    return result


def _resolve_balance_adjustment(
    balance_value: float,
    known_external_incoming: float,
    known_exports: float,
    epsilon: float,
) -> tuple[float, float]:
    net_external_requirement = float(balance_value) + float(known_exports) - float(known_external_incoming)
    unknown_source = max(net_external_requirement, 0.0)
    unknown_target = max(-net_external_requirement, 0.0)
    if unknown_source <= epsilon:
        unknown_source = 0.0
    if unknown_target <= epsilon:
        unknown_target = 0.0
    return unknown_source, unknown_target


def _chem_weights(
    category_totals: dict[str, float],
    fallback: dict[str, float],
    epsilon: float,
) -> dict[str, float]:
    total = sum(float(value) for value in category_totals.values())
    if total <= epsilon:
        return dict(fallback)
    return {
        category: float(value) / total
        for category, value in category_totals.items()
        if float(value) > epsilon
    }


def _distribute(value: float, weights: dict[str, float], epsilon: float) -> dict[str, float]:
    return {
        category: value * share
        for category, share in weights.items()
        if value * share > epsilon
    }


def _country_key(stage: str, country_id: int) -> str:
    return f"{stage}:country:{country_id}"


def _chem_key(stage: str, country_id: int, chemistry: str) -> str:
    return f"{stage}:chem:{country_id}:{chemistry}"


def _aggregate_chem_key(stage: str, chemistry: str) -> str:
    return f"{stage}:chem_aggregate:{chemistry}"


def _special_key(stage: str, slug: str) -> str:
    return f"{stage}:special:{slug}"


def _continent_key(stage: str, region: str) -> str:
    return f"{stage}:continent:{region.lower().replace(' ', '_')}"


class SankeyBuilder:
    def __init__(
        self,
        id_to_name: dict[int, str],
        id_to_iso3: dict[int, str],
        color_map: dict[int, str],
        region_map: dict[int, str] | None = None,
    ) -> None:
        self.id_to_name = id_to_name
        self.id_to_iso3 = id_to_iso3
        self.color_map = color_map
        self.region_map = region_map or {}
        self.nodes: dict[str, NodeSpec] = {}
        self.links: list[LinkSpec] = []

    def country_name(self, country_id: int) -> str:
        return self.id_to_name.get(country_id, str(country_id))

    def country_hover(self, country_id: int) -> str:
        name = self.country_name(country_id)
        iso3 = self.id_to_iso3.get(country_id, "")
        return f"{name} ({iso3})" if iso3 else name

    def country_region(self, country_id: int) -> str:
        return self.region_map.get(country_id, "Unknown") or "Unknown"

    def ensure_country_node(self, stage: str, country_id: int, suffix: str = "") -> str:
        label = f"{self.country_name(country_id)}{suffix}"
        key = _country_key(stage, country_id) if not suffix else f"{_country_key(stage, country_id)}:{suffix}"
        if key not in self.nodes:
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=label,
                color=self.color_map.get(country_id, "#7f8c8d"),
                kind="regular",
                hover=self.country_hover(country_id),
                region=self.country_region(country_id),
            )
        return key

    def ensure_chem_node(self, stage: str, country_id: int, chemistry: str, aggregate: bool = False) -> str:
        if aggregate:
            key = _aggregate_chem_key(stage, chemistry)
            hover = chemistry
            label = chemistry
            region = "Unknown"
        else:
            key = _chem_key(stage, country_id, chemistry)
            hover = f"{self.country_hover(country_id)} / {chemistry}"
            label = f"{self.country_name(country_id)} / {chemistry}"
            region = self.country_region(country_id)
        if key not in self.nodes:
            color = "#34C759" if aggregate else self.color_map.get(country_id, "#7f8c8d")
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=label,
                color=color,
                kind="regular",
                hover=hover,
                region=region,
            )
        return key

    def ensure_special_node(self, stage: str, slug: str, label: str, color: str, kind: str) -> str:
        key = _special_key(stage, slug)
        if key not in self.nodes:
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=label,
                color=color,
                kind=kind,
                hover=label,
                region="Unknown",
            )
        return key

    def add_link(self, source_key: str, target_key: str, value: float, epsilon: float, color: str | None = None) -> None:
        if value <= epsilon:
            return
        source_color = self.nodes[source_key].color if source_key in self.nodes else "#7f8c8d"
        self.links.append(
            LinkSpec(
                source=source_key,
                target=target_key,
                value=float(value),
                color=color or _hex_to_rgba(source_color),
            )
        )


def _aggregate_links(links: list[LinkSpec], epsilon: float) -> list[LinkSpec]:
    buckets: dict[tuple[str, str, str], float] = {}
    for link in links:
        key = (link.source, link.target, link.color)
        buckets[key] = buckets.get(key, 0.0) + float(link.value)
    return [
        LinkSpec(source=source, target=target, value=value, color=color)
        for (source, target, color), value in buckets.items()
        if value > epsilon
    ]


def _plotly_safe_token(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in str(value))


def _node_values(nodes: dict[str, NodeSpec], links: list[LinkSpec]) -> dict[str, float]:
    incoming: dict[str, float] = {}
    outgoing: dict[str, float] = {}
    for link in links:
        incoming[link.target] = incoming.get(link.target, 0.0) + link.value
        outgoing[link.source] = outgoing.get(link.source, 0.0) + link.value
    return {
        key: max(incoming.get(key, 0.0), outgoing.get(key, 0.0))
        for key in nodes
    }


def _stage_nodes(nodes: dict[str, NodeSpec]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for key, node in nodes.items():
        grouped.setdefault(node.stage, []).append(key)
    return grouped


def _is_display_node(node: NodeSpec) -> bool:
    return node.kind in {"regular", "aggregate"}


def _region_rank(region: str) -> tuple[int, str]:
    try:
        return (REGION_ORDER.index(region), region)
    except ValueError:
        return (len(REGION_ORDER), region)


def _default_special_position(stage_keys: list[str], nodes: dict[str, NodeSpec]) -> str:
    has_source_special = any(nodes[key].kind == "source_special" for key in stage_keys)
    has_sink_special = any(nodes[key].kind == "sink_special" for key in stage_keys)
    if has_source_special and not has_sink_special:
        return "first"
    if has_sink_special and not has_source_special:
        return "last"
    return DEFAULT_SPECIAL_POSITION


def _resolve_special_positions(
    nodes: dict[str, NodeSpec],
    special_positions: dict[str, str] | None,
) -> dict[str, str]:
    grouped = _stage_nodes(nodes)
    resolved: dict[str, str] = {}
    for stage in STAGE_ORDER:
        requested = (special_positions or {}).get(stage)
        if requested is None or requested == "":
            resolved[stage] = _default_special_position(grouped.get(stage, []), nodes)
            continue
        if requested not in SPECIAL_NODE_POSITIONS:
            raise ValueError(
                f"Unsupported special node position for {stage}: {requested}. "
                f"Choose one of {', '.join(SPECIAL_NODE_POSITIONS)}."
            )
        resolved[stage] = requested
    return resolved


def _sort_stage_nodes(
    stage: str,
    stage_keys: list[str],
    nodes: dict[str, NodeSpec],
    values: dict[str, float],
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
) -> list[str]:
    source_specials = [key for key in stage_keys if nodes[key].kind == "source_special"]
    regular_keys = [key for key in stage_keys if nodes[key].kind == "regular"]
    aggregate_keys = [key for key in stage_keys if nodes[key].kind == "aggregate"]
    sink_specials = [key for key in stage_keys if nodes[key].kind == "sink_special"]

    source_specials.sort(key=lambda key: (-values.get(key, 0.0), nodes[key].label))
    sink_specials.sort(key=lambda key: (-values.get(key, 0.0), nodes[key].label))

    sort_mode = sort_modes.get(stage, DEFAULT_SORT_MODE)
    if sort_mode == "manual":
        preferred = stage_orders.get(stage, [])
        key_by_label = {nodes[key].label: key for key in regular_keys}
        ordered_regulars = [key_by_label[label] for label in preferred if label in key_by_label]
        leftovers = [key for key in regular_keys if key not in ordered_regulars]
        leftovers.sort(key=lambda key: (-values.get(key, 0.0), nodes[key].label))
        regular_sorted = ordered_regulars + leftovers
    elif sort_mode == "continent":
        regular_sorted = sorted(
            regular_keys,
            key=lambda key: (_region_rank(nodes[key].region), -values.get(key, 0.0), nodes[key].label),
        )
    else:
        regular_sorted = sorted(regular_keys, key=lambda key: (-values.get(key, 0.0), nodes[key].label))

    aggregate_keys.sort(key=lambda key: nodes[key].label)
    special_keys = source_specials + sink_specials
    if special_positions.get(stage, DEFAULT_SPECIAL_POSITION) == "last":
        return regular_sorted + aggregate_keys + special_keys
    return special_keys + regular_sorted + aggregate_keys


def _px_per_unit_from_reference(reference_qty: float) -> float:
    safe_qty = max(float(reference_qty), 1.0)
    return REFERENCE_NODE_HEIGHT_PX / safe_qty


def _layout(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    reference_qty: float,
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    epsilon: float,
) -> tuple[list[str], list[float], list[float], dict[str, float], int, float]:
    values = _node_values(nodes, links)
    grouped = _stage_nodes(nodes)
    px_per_unit = _px_per_unit_from_reference(reference_qty)
    stage_stack_heights: dict[str, float] = {}
    node_heights: dict[str, float] = {}
    sorted_nodes_by_stage: dict[str, list[str]] = {}
    for stage in STAGE_ORDER:
        sorted_keys = _sort_stage_nodes(
            stage,
            grouped.get(stage, []),
            nodes,
            values,
            sort_modes,
            stage_orders,
            special_positions,
        )
        sorted_nodes_by_stage[stage] = sorted_keys
        total_height = 0.0
        for index, key in enumerate(sorted_keys):
            height = values.get(key, 0.0) * px_per_unit
            node_heights[key] = height
            total_height += height
            if index < len(sorted_keys) - 1:
                total_height += GAP_PX
        stage_stack_heights[stage] = total_height
    plot_height = max(
        max(stage_stack_heights.values(), default=0.0),
        float(MIN_STAGE_HEIGHT_PX - TOP_BAND_PX - BOTTOM_BAND_PX),
    )
    figure_height = int(
        max(
            MIN_STAGE_HEIGHT_PX,
            plot_height + TOP_BAND_PX + BOTTOM_BAND_PX,
        )
    )
    plot_height = float(figure_height - TOP_BAND_PX - BOTTOM_BAND_PX)

    ordered_keys: list[str] = []
    x_positions: list[float] = []
    y_positions: list[float] = []
    for stage in STAGE_ORDER:
        stage_keys = sorted_nodes_by_stage.get(stage, [])
        if not stage_keys:
            continue
        current_y = 0.0
        for key in stage_keys:
            ordered_keys.append(key)
            x_positions.append(X_MAP[stage])
            center_y = current_y + (node_heights[key] / 2.0)
            y_positions.append(center_y / plot_height if plot_height > epsilon else 0.0)
            current_y += node_heights[key] + GAP_PX
    tallest_stage_content = max(stage_stack_heights.values(), default=0.0)
    return ordered_keys, x_positions, y_positions, values, figure_height, tallest_stage_content


def _prune_zero_value_nodes(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    epsilon: float,
) -> tuple[dict[str, NodeSpec], list[LinkSpec]]:
    values = _node_values(nodes, links)
    kept_keys = {
        key
        for key, value in values.items()
        if float(value) > epsilon
    }
    pruned_nodes = {
        key: node
        for key, node in nodes.items()
        if key in kept_keys
    }
    pruned_links = [
        link
        for link in links
        if link.source in kept_keys and link.target in kept_keys and link.value > epsilon
    ]
    return pruned_nodes, pruned_links


def _build_summary(nodes: dict[str, NodeSpec], links: list[LinkSpec]) -> list[dict[str, Any]]:
    values = _node_values(nodes, links)
    grouped = _stage_nodes(nodes)
    summary: list[dict[str, Any]] = []
    for stage in STAGE_ORDER:
        stage_keys = grouped.get(stage, [])
        regular_keys = [key for key in stage_keys if _is_display_node(nodes[key])]
        summary.append(
            {
                "id": stage,
                "label": STAGE_LABELS[stage],
                "nodeCount": len(regular_keys),
                "total": round(sum(values.get(key, 0.0) for key in regular_keys), 3),
            }
        )
    return summary


def _build_stage_controls(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    aggregate_counts: dict[str, int],
) -> dict[str, dict[str, Any]]:
    values = _node_values(nodes, links)
    grouped = _stage_nodes(nodes)
    controls: dict[str, dict[str, Any]] = {}
    for stage in STAGE_ORDER:
        stage_keys = _sort_stage_nodes(
            stage,
            grouped.get(stage, []),
            nodes,
            values,
            sort_modes,
            stage_orders,
            special_positions,
        )
        regular_keys = [key for key in stage_keys if nodes[key].kind == "regular"]
        special_keys = [key for key in stage_keys if nodes[key].kind in {"source_special", "sink_special"}]
        sort_mode = sort_modes.get(stage, DEFAULT_SORT_MODE)
        max_aggregate_count = max(len(regular_keys) - 1, 0)
        controls[stage] = {
            "label": STAGE_LABELS[stage],
            "sortMode": sort_mode,
            "specialPosition": special_positions.get(stage, DEFAULT_SPECIAL_POSITION),
            "hasSpecialNodes": bool(special_keys),
            "specialNodeCount": len(special_keys),
            "aggregateCount": aggregate_counts.get(stage, 0) if sort_mode != "continent" else 0,
            "maxAggregateCount": max_aggregate_count,
            "items": [
                {
                    "label": nodes[key].label,
                    "value": round(values.get(key, 0.0), 3),
                    "group": nodes[key].region or "Unknown",
                    "groupColor": REGION_COLORS.get(nodes[key].region or "Unknown", REGION_COLORS["Unknown"]),
                }
                for key in regular_keys
            ],
        }
    return controls


def _validate_aggregate_counts(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    aggregate_counts: dict[str, int] | None,
) -> dict[str, int]:
    values = _node_values(nodes, links)
    grouped = _stage_nodes(nodes)
    resolved: dict[str, int] = {}
    for stage in STAGE_ORDER:
        requested = int((aggregate_counts or {}).get(stage, 0) or 0)
        if requested < 0:
            raise ValueError(f"Aggregate count for {stage} must be 0 or greater.")
        sort_mode = sort_modes.get(stage, DEFAULT_SORT_MODE)
        if sort_mode == "continent":
            resolved[stage] = 0
            continue
        ordered_keys = _sort_stage_nodes(
            stage,
            grouped.get(stage, []),
            nodes,
            values,
            sort_modes,
            stage_orders,
            special_positions,
        )
        regular_count = len([key for key in ordered_keys if nodes[key].kind == "regular"])
        max_count = max(regular_count - 1, 0)
        if requested > max_count:
            raise ValueError(f"Aggregate count for {stage} must be between 0 and {max_count}.")
        resolved[stage] = requested
    return resolved


def _apply_continent_aggregation(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    stage: str,
    epsilon: float,
) -> tuple[dict[str, NodeSpec], list[LinkSpec]]:
    values = _node_values(nodes, links)
    grouped = _stage_nodes(nodes)
    regular_keys = [key for key in grouped.get(stage, []) if nodes[key].kind == "regular"]
    if not regular_keys:
        return nodes, links

    transformed_nodes = dict(nodes)
    members_by_region: dict[str, list[str]] = {}
    for key in regular_keys:
        region = nodes[key].region or "Unknown"
        members_by_region.setdefault(region, []).append(key)

    replacement_map: dict[str, str] = {}
    for region, member_keys in members_by_region.items():
        region_key = _continent_key(stage, region)
        member_lines = [
            f"{nodes[key].label} ({values.get(key, 0.0):,.0f} t)"
            for key in sorted(member_keys, key=lambda item: (-values.get(item, 0.0), nodes[item].label))
        ]
        transformed_nodes[region_key] = NodeSpec(
            key=region_key,
            stage=stage,
            label=region,
            color=REGION_COLORS.get(region, REGION_COLORS["Unknown"]),
            kind="regular",
            hover=f"{region}<br>" + "<br>".join(member_lines),
            region=region,
        )
        for key in member_keys:
            replacement_map[key] = region_key

    remapped_links: list[LinkSpec] = []
    for link in links:
        source = replacement_map.get(link.source, link.source)
        target = replacement_map.get(link.target, link.target)
        if source == target:
            continue
        color = link.color
        if source in transformed_nodes and source.startswith(f"{stage}:continent:"):
            color = _hex_to_rgba(transformed_nodes[source].color, 0.42)
        remapped_links.append(LinkSpec(source=source, target=target, value=link.value, color=color))

    for key in regular_keys:
        transformed_nodes.pop(key, None)
    return transformed_nodes, _aggregate_links(remapped_links, epsilon)


def _apply_stage_aggregation(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    aggregate_counts: dict[str, int],
    view_mode: str,
    epsilon: float,
) -> tuple[dict[str, NodeSpec], list[LinkSpec]]:
    transformed_nodes = dict(nodes)
    transformed_links = list(links)
    for stage in STAGE_ORDER:
        sort_mode = sort_modes.get(stage, DEFAULT_SORT_MODE)
        if sort_mode == "continent":
            transformed_nodes, transformed_links = _apply_continent_aggregation(
                transformed_nodes,
                transformed_links,
                stage,
                epsilon,
            )
            continue
        tail_count = aggregate_counts.get(stage, 0)
        if tail_count <= 0:
            continue
        values = _node_values(transformed_nodes, transformed_links)
        grouped = _stage_nodes(transformed_nodes)
        ordered_keys = _sort_stage_nodes(
            stage,
            grouped.get(stage, []),
            transformed_nodes,
            values,
            sort_modes,
            stage_orders,
            special_positions,
        )
        regular_keys = [key for key in ordered_keys if transformed_nodes[key].kind == "regular"]
        if len(regular_keys) <= 1:
            continue
        tail_keys = regular_keys[-tail_count:]
        if not tail_keys:
            continue
        tail_labels = [transformed_nodes[key].label for key in tail_keys]
        aggregate_label = (
            f"Other {len(tail_keys)} Countries"
            if view_mode == "country"
            else f"Other {len(tail_keys)} Nodes"
        )
        aggregate_key = f"{stage}:aggregate:tail"
        transformed_nodes[aggregate_key] = NodeSpec(
            key=aggregate_key,
            stage=stage,
            label=aggregate_label,
            color=SPECIAL_COLORS["aggregate"],
            kind="aggregate",
            hover="Aggregated tail:<br>" + "<br>".join(tail_labels),
            region="Unknown",
        )
        remapped: list[LinkSpec] = []
        for link in transformed_links:
            source = aggregate_key if link.source in tail_keys else link.source
            target = aggregate_key if link.target in tail_keys else link.target
            if source == target:
                continue
            color = link.color
            if source == aggregate_key:
                color = _hex_to_rgba(SPECIAL_COLORS["aggregate"], 0.42)
            remapped.append(LinkSpec(source=source, target=target, value=link.value, color=color))
        for key in tail_keys:
            transformed_nodes.pop(key, None)
        transformed_links = _aggregate_links(remapped, epsilon)
    return transformed_nodes, transformed_links


def _build_figure(
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    year: int,
    view_mode: str,
    reference_qty: float,
    sort_modes: dict[str, str],
    stage_orders: dict[str, list[str]],
    special_positions: dict[str, str],
    metal: str,
    theme: str,
    epsilon: float,
) -> dict[str, Any]:
    aggregated = _aggregate_links(links, epsilon)
    ordered_keys, x_positions, y_positions, values, height, tallest_stage_content = _layout(
        nodes,
        aggregated,
        reference_qty,
        sort_modes,
        stage_orders,
        special_positions,
        epsilon,
    )
    plot_domain_top = TOP_BAND_PX / height if height > epsilon else 0.0
    plot_domain_bottom = 1.0 - (BOTTOM_BAND_PX / height if height > epsilon else 0.0)
    reference_label = f"Reference Node: {reference_qty:,.0f} t"
    key_to_index = {key: index for index, key in enumerate(ordered_keys)}
    labels: list[str] = []
    hover_labels: list[str] = []
    colors: list[str] = []
    for key in ordered_keys:
        node = nodes[key]
        labels.append(node.label if node.kind != "sink_special" or values.get(key, 0.0) > epsilon else "")
        hover_labels.append(f"{node.hover}<br>{values.get(key, 0.0):,.0f} t")
        colors.append(node.color)

    reference_bottom_px_total = TOP_BAND_PX + tallest_stage_content
    reference_top_px_total = max(reference_bottom_px_total - REFERENCE_NODE_HEIGHT_PX, TOP_BAND_PX)
    reference_y0 = max(0.0, 1.0 - (reference_bottom_px_total / height))
    reference_y1 = min(1.0, 1.0 - (reference_top_px_total / height))
    reference_y = (reference_y0 + reference_y1) / 2
    reference_x0 = max(0.0, REFERENCE_NODE_CENTER_X - REFERENCE_NODE_HALF_WIDTH_PAPER)
    reference_x1 = min(1.0, REFERENCE_NODE_CENTER_X + REFERENCE_NODE_HALF_WIDTH_PAPER)

    figure = go.Figure(
        go.Sankey(
            ids=[_plotly_safe_token(key) for key in ordered_keys],
            uid=_plotly_safe_token(f"{metal}-{view_mode}"),
            arrangement="fixed",
            domain={"x": [0.0, 1.0], "y": [plot_domain_top, plot_domain_bottom]},
            node={
                "label": labels,
                "x": x_positions,
                "y": y_positions,
                "pad": int(PLOTLY_NODE_PAD_PX),
                "thickness": 20,
                "line": {"color": "rgba(0,0,0,0)", "width": 0},
                "color": colors,
                "customdata": hover_labels,
                "hovertemplate": "%{customdata}<extra></extra>",
            },
            link={
                "source": [key_to_index[link.source] for link in aggregated],
                "target": [key_to_index[link.target] for link in aggregated],
                "value": [link.value for link in aggregated],
                "color": [link.color for link in aggregated],
            },
        )
    )
    figure.update_layout(
        font={"color": BODY_TEXT_BY_THEME[theme], "family": BODY_FONT_FAMILY, "size": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 6, "r": 6, "t": 8, "b": 16},
        height=height,
        annotations=[
            *[
                {
                    "xref": "paper",
                    "yref": "paper",
                    "x": X_MAP[stage],
                    "y": 1 - ((TOP_BAND_PX * STAGE_TITLE_Y_RATIO) / height),
                    "text": STAGE_NAMES[stage],
                    "showarrow": False,
                    "xanchor": "center",
                    "yanchor": "middle",
                    "align": "center",
                    "font": {
                        "family": DISPLAY_FONT_FAMILY,
                        "size": 12,
                        "color": TITLE_TEXT_BY_THEME[theme],
                    },
                }
                for stage in STAGE_ORDER
            ],
            {
                "xref": "paper",
                "yref": "paper",
                "x": max(0.0, reference_x0 - REFERENCE_LABEL_GAP_PAPER),
                "y": reference_y,
                "text": reference_label,
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "middle",
                "align": "right",
                "font": {
                    "family": BODY_FONT_FAMILY,
                    "size": 12,
                    "color": REFERENCE_TEXT_BY_THEME[theme],
                },
            },
        ],
        shapes=[
            {
                "type": "rect",
                "xref": "paper",
                "yref": "paper",
                "x0": reference_x0,
                "x1": reference_x1,
                "y0": reference_y0,
                "y1": reference_y1,
                "line": {"width": 0},
                "fillcolor": SPECIAL_COLORS["reference"],
                "layer": "above",
            }
        ],
    )
    return figure.to_plotly_json()


def add_country_trade_section(
    builder: SankeyBuilder,
    *,
    epsilon: float,
    source_stage: str,
    post_stage: str,
    target_stage: str,
    source_totals: dict[int, float],
    trade_supply: dict[int, float],
    direct_local: dict[int, float],
    balance_map: dict[int, float],
    target_totals: dict[int, float],
    known_trade: tuple[Any, ...],
    labels: dict[str, str],
    non_source_stage: str | None = None,
    unknown_source_stage: str | None = None,
    non_target_stage: str | None = None,
    unknown_target_stage: str | None = None,
) -> None:
    source_totals = _clip(source_totals, epsilon)
    trade_supply = _clip(trade_supply, epsilon)
    direct_local = _clip(direct_local, epsilon)
    balance_map = _clip(balance_map, epsilon)
    target_totals = _clip(target_totals, epsilon)

    source_ids = set(source_totals)
    target_ids = set(target_totals)
    external_incoming: dict[int, float] = {country_id: 0.0 for country_id in target_ids}
    known_exports: dict[int, float] = {country_id: 0.0 for country_id in target_ids}

    for country_id in source_totals:
        builder.ensure_country_node(source_stage, country_id)

    exporter_targets: dict[int, dict[int, float]] = {}
    exporter_non_target: dict[int, float] = {}
    non_source_imports: dict[int, float] = {}
    for flow in known_trade:
        if flow.importer in target_ids:
            if flow.exporter in source_ids:
                exporter_targets.setdefault(flow.exporter, {})
                exporter_targets[flow.exporter][flow.importer] = (
                    exporter_targets[flow.exporter].get(flow.importer, 0.0) + flow.value
                )
            else:
                non_source_imports[flow.importer] = non_source_imports.get(flow.importer, 0.0) + flow.value
        elif flow.exporter in source_ids:
            exporter_non_target[flow.exporter] = exporter_non_target.get(flow.exporter, 0.0) + flow.value

    non_target_key = builder.ensure_special_node(
        non_target_stage or post_stage,
        labels["non_target_slug"],
        labels["non_target"],
        SPECIAL_COLORS["non_target"],
        "sink_special",
    )
    non_source_key = builder.ensure_special_node(
        non_source_stage or source_stage,
        labels["non_source_slug"],
        labels["non_source"],
        SPECIAL_COLORS["non_source"],
        "source_special",
    )
    unknown_source_key = builder.ensure_special_node(
        unknown_source_stage or source_stage,
        labels["unknown_source_slug"],
        labels["unknown_source"],
        SPECIAL_COLORS["unknown_source"],
        "source_special",
    )
    unknown_target_key = builder.ensure_special_node(
        unknown_target_stage or target_stage,
        labels["unknown_target_slug"],
        labels["unknown_target"],
        SPECIAL_COLORS["unknown_target"],
        "sink_special",
    )

    for country_id, value in direct_local.items():
        if value <= epsilon:
            continue
        source_key = builder.ensure_country_node(source_stage, country_id)
        if country_id in target_ids:
            post_key = builder.ensure_country_node(post_stage, country_id)
            builder.add_link(source_key, post_key, value, epsilon)
        else:
            builder.add_link(source_key, non_target_key, value, epsilon)

    for exporter, total in trade_supply.items():
        source_key = builder.ensure_country_node(source_stage, exporter)
        target_map = exporter_targets.get(exporter, {})
        known_total = sum(target_map.values()) + exporter_non_target.get(exporter, 0.0)
        scale = min(1.0, total / known_total) if known_total > epsilon else 1.0
        used = 0.0
        exporter_known_exports = 0.0
        for importer, value in target_map.items():
            scaled = value * scale
            if scaled <= epsilon:
                continue
            post_key = builder.ensure_country_node(post_stage, importer)
            builder.add_link(source_key, post_key, scaled, epsilon)
            if importer != exporter:
                external_incoming[importer] = external_incoming.get(importer, 0.0) + scaled
                exporter_known_exports += scaled
            used += scaled
        non_target_value = exporter_non_target.get(exporter, 0.0) * scale
        if non_target_value > epsilon:
            builder.add_link(source_key, non_target_key, non_target_value, epsilon)
            used += non_target_value
            exporter_known_exports += non_target_value
        self_value = max(total - used, 0.0)
        if self_value > epsilon:
            if exporter in target_ids:
                post_key = builder.ensure_country_node(post_stage, exporter)
                builder.add_link(source_key, post_key, self_value, epsilon)
            else:
                builder.add_link(source_key, non_target_key, self_value, epsilon)
                exporter_known_exports += self_value
        if exporter in target_ids:
            known_exports[exporter] = known_exports.get(exporter, 0.0) + exporter_known_exports

    for importer, value in non_source_imports.items():
        if value <= epsilon:
            continue
        post_key = builder.ensure_country_node(post_stage, importer)
        builder.add_link(non_source_key, post_key, value, epsilon)
        external_incoming[importer] = external_incoming.get(importer, 0.0) + value

    for country_id, target_total in target_totals.items():
        post_key = builder.ensure_country_node(post_stage, country_id)
        target_key = builder.ensure_country_node(target_stage, country_id)
        trade_need = max(target_total - direct_local.get(country_id, 0.0), 0.0)
        balance_value = balance_map.get(country_id, trade_need - trade_supply.get(country_id, 0.0))
        gap, excess = _resolve_balance_adjustment(
            balance_value,
            external_incoming.get(country_id, 0.0),
            known_exports.get(country_id, 0.0),
            epsilon,
        )
        if gap > epsilon:
            builder.add_link(unknown_source_key, post_key, gap, epsilon)
        builder.add_link(post_key, target_key, target_total, epsilon)
        if excess > epsilon:
            builder.add_link(post_key, unknown_target_key, excess, epsilon)


def add_shared_pool_chem_trade_section(
    builder: SankeyBuilder,
    *,
    epsilon: float,
    source_stage: str,
    post_stage: str,
    target_stage: str,
    source_totals: dict[int, float],
    trade_supply: dict[int, float],
    target_totals_by_category: dict[str, dict[int, float]],
    balance_by_category: dict[str, dict[int, float]],
    known_trade: tuple[Any, ...],
    source_role: str,
    target_role: str,
    aggregate_display: bool,
    non_source_stage: str | None = None,
    unknown_source_stage: str | None = None,
    non_target_stage: str | None = None,
    unknown_target_stage: str | None = None,
) -> None:
    categories = tuple(target_totals_by_category.keys())
    if not categories:
        return

    source_totals = _clip(source_totals, epsilon)
    trade_supply = _clip(trade_supply, epsilon)
    target_totals_by_category = {
        category: _clip(values, epsilon)
        for category, values in target_totals_by_category.items()
    }
    balance_by_category = {
        category: _clip(values, epsilon)
        for category, values in balance_by_category.items()
    }

    target_ids = set()
    for mapping in target_totals_by_category.values():
        target_ids.update(mapping.keys())
    source_ids = set(source_totals)

    global_totals = {
        category: sum(target_totals_by_category.get(category, {}).values())
        for category in categories
    }
    positive_categories = {category: total for category, total in global_totals.items() if total > epsilon}
    if positive_categories:
        fallback = _chem_weights(positive_categories, {categories[0]: 1.0}, epsilon)
    else:
        fallback = {category: 1.0 / len(categories) for category in categories}

    target_weights = {
        country_id: _chem_weights(
            {
                category: target_totals_by_category.get(category, {}).get(country_id, 0.0)
                for category in categories
            },
            fallback,
            epsilon,
        )
        for country_id in target_ids
    }

    target_totals: dict[tuple[int, str], float] = {}
    for category in categories:
        for country_id, value in target_totals_by_category.get(category, {}).items():
            if value > epsilon:
                target_totals[(country_id, category)] = value

    non_source_key = builder.ensure_special_node(
        non_source_stage or source_stage,
        f"non_source_{source_role.lower()}",
        f"Non-{source_role}",
        SPECIAL_COLORS["non_source"],
        "source_special",
    )
    unknown_source_key = builder.ensure_special_node(
        unknown_source_stage or source_stage,
        f"unknown_source_{source_role.lower()}",
        "Unknown Source",
        SPECIAL_COLORS["unknown_source"],
        "source_special",
    )
    non_target_key = builder.ensure_special_node(
        non_target_stage or post_stage,
        f"non_target_{target_role.lower()}",
        f"Non-{target_role}",
        SPECIAL_COLORS["non_target"],
        "sink_special",
    )
    unknown_target_key = builder.ensure_special_node(
        unknown_target_stage or target_stage,
        f"unknown_target_{target_role.lower()}",
        "Unknown Destination",
        SPECIAL_COLORS["unknown_target"],
        "sink_special",
    )
    non_source_keys = {category: non_source_key for category in categories}
    unknown_source_keys = {category: unknown_source_key for category in categories}
    non_target_keys = {category: non_target_key for category in categories}
    unknown_target_keys = {category: unknown_target_key for category in categories}

    exporter_targets: dict[int, dict[tuple[int, str], float]] = {}
    exporter_non_target: dict[int, dict[str, float]] = {}
    non_source_imports: dict[tuple[int, str], float] = {}
    external_incoming: dict[tuple[int, str], float] = {key: 0.0 for key in target_totals}
    known_exports: dict[tuple[int, str], float] = {key: 0.0 for key in target_totals}

    for flow in known_trade:
        if flow.importer in target_ids:
            weights = target_weights[flow.importer]
            if flow.exporter in source_ids:
                exporter_targets.setdefault(flow.exporter, {})
                for category, amount in _distribute(flow.value, weights, epsilon).items():
                    target_key = (flow.importer, category)
                    exporter_targets[flow.exporter][target_key] = exporter_targets[flow.exporter].get(target_key, 0.0) + amount
            else:
                for category, amount in _distribute(flow.value, weights, epsilon).items():
                    target_key = (flow.importer, category)
                    non_source_imports[target_key] = non_source_imports.get(target_key, 0.0) + amount
        elif flow.exporter in source_ids:
            exporter_non_target.setdefault(flow.exporter, {})
            for category, amount in _distribute(flow.value, fallback, epsilon).items():
                exporter_non_target[flow.exporter][category] = exporter_non_target[flow.exporter].get(category, 0.0) + amount

    for country_id in source_totals:
        builder.ensure_country_node(source_stage, country_id)

    for exporter, total in trade_supply.items():
        source_key = builder.ensure_country_node(source_stage, exporter)
        target_map = exporter_targets.get(exporter, {})
        non_target_map = exporter_non_target.get(exporter, {})
        known_total = sum(target_map.values()) + sum(non_target_map.values())
        scale = min(1.0, total / known_total) if known_total > epsilon else 1.0
        used = 0.0
        exporter_known_exports: dict[str, float] = {category: 0.0 for category in categories}
        for (importer, category), value in target_map.items():
            scaled = value * scale
            if scaled <= epsilon:
                continue
            post_key = builder.ensure_country_node(post_stage, importer)
            builder.add_link(source_key, post_key, scaled, epsilon)
            if importer != exporter:
                external_incoming[(importer, category)] = external_incoming.get((importer, category), 0.0) + scaled
                exporter_known_exports[category] = exporter_known_exports.get(category, 0.0) + scaled
            used += scaled
        for category, value in non_target_map.items():
            scaled = value * scale
            if scaled <= epsilon:
                continue
            builder.add_link(source_key, non_target_keys[category], scaled, epsilon)
            used += scaled
            exporter_known_exports[category] = exporter_known_exports.get(category, 0.0) + scaled
        self_value = max(total - used, 0.0)
        if self_value > epsilon:
            if exporter in target_ids:
                for category, amount in _distribute(self_value, target_weights[exporter], epsilon).items():
                    post_key = builder.ensure_country_node(post_stage, exporter)
                    builder.add_link(source_key, post_key, amount, epsilon)
            else:
                for category, amount in _distribute(self_value, fallback, epsilon).items():
                    builder.add_link(source_key, non_target_keys[category], amount, epsilon)
                    exporter_known_exports[category] = exporter_known_exports.get(category, 0.0) + amount
        if exporter in target_ids:
            for category, value in exporter_known_exports.items():
                known_exports[(exporter, category)] = known_exports.get((exporter, category), 0.0) + value

    for (importer, category), value in non_source_imports.items():
        if value <= epsilon:
            continue
        post_key = builder.ensure_country_node(post_stage, importer)
        builder.add_link(non_source_keys[category], post_key, value, epsilon)
        external_incoming[(importer, category)] = external_incoming.get((importer, category), 0.0) + value

    for (country_id, category), target_total in target_totals.items():
        post_key = builder.ensure_country_node(post_stage, country_id)
        target_key = builder.ensure_chem_node(target_stage, country_id, category, aggregate=aggregate_display)
        allocated_supply = target_weights[country_id].get(category, 0.0) * source_totals.get(country_id, 0.0)
        balance_value = balance_by_category.get(category, {}).get(country_id, target_total - allocated_supply)
        gap, excess = _resolve_balance_adjustment(
            balance_value,
            external_incoming.get((country_id, category), 0.0),
            known_exports.get((country_id, category), 0.0),
            epsilon,
        )
        if gap > epsilon:
            builder.add_link(unknown_source_keys[category], post_key, gap, epsilon)
        builder.add_link(post_key, target_key, target_total, epsilon)
        if excess > epsilon:
            builder.add_link(post_key, unknown_target_keys[category], excess, epsilon)


def add_stage_sink_links(
    builder: SankeyBuilder,
    *,
    epsilon: float,
    source_stage: str,
    sink_stage: str,
    values: dict[int, float],
    slug: str,
    label: str,
    color: str,
) -> None:
    sink_key = builder.ensure_special_node(sink_stage, slug, label, color, "sink_special")
    for country_id, value in _clip(values, epsilon).items():
        source_key = builder.ensure_country_node(source_stage, country_id)
        builder.add_link(source_key, sink_key, value, epsilon)


def make_payload(
    *,
    nodes: dict[str, NodeSpec],
    links: list[LinkSpec],
    year: int,
    metal: str,
    view_mode: str,
    reference_qty: float,
    sort_modes: dict[str, str] | None,
    stage_orders: dict[str, list[str]] | None,
    notes: list[str],
    dataset_status: dict[str, Any],
    epsilon: float,
    special_positions: dict[str, str] | None = None,
    aggregate_counts: dict[str, int] | None = None,
    theme: str = DEFAULT_THEME,
) -> dict[str, Any]:
    resolved_view_mode = resolve_view_mode(view_mode)
    if reference_qty <= 0:
        raise ValueError("reference_qty must be greater than 0.")
    if theme not in THEME_MODES:
        raise ValueError(f"Unsupported theme: {theme}")

    resolved_sort_modes = {
        stage: (sort_modes or {}).get(stage, DEFAULT_SORT_MODE)
        for stage in STAGE_ORDER
    }
    invalid_modes = [stage for stage, mode in resolved_sort_modes.items() if mode not in SORT_MODES]
    if invalid_modes:
        raise ValueError(f"Unsupported sort mode for stage(s): {', '.join(invalid_modes)}")
    resolved_stage_orders = {
        stage: list((stage_orders or {}).get(stage, []))
        for stage in STAGE_ORDER
    }

    aggregated = _aggregate_links(links, epsilon)
    visible_nodes, visible_links = _prune_zero_value_nodes(nodes, aggregated, epsilon)
    resolved_special_positions = _resolve_special_positions(visible_nodes, special_positions)
    resolved_aggregate_counts = _validate_aggregate_counts(
        visible_nodes,
        visible_links,
        resolved_sort_modes,
        resolved_stage_orders,
        resolved_special_positions,
        aggregate_counts,
    )
    figure_nodes, figure_links = _apply_stage_aggregation(
        visible_nodes,
        visible_links,
        resolved_sort_modes,
        resolved_stage_orders,
        resolved_special_positions,
        resolved_aggregate_counts,
        resolved_view_mode,
        epsilon,
    )
    return {
        "metal": metal,
        "theme": theme,
        "year": year,
        "viewMode": resolved_view_mode,
        "referenceQuantity": reference_qty,
        "aggregateCounts": resolved_aggregate_counts,
        "specialPositions": resolved_special_positions,
        "figure": _build_figure(
            figure_nodes,
            figure_links,
            year,
            resolved_view_mode,
            reference_qty,
            resolved_sort_modes,
            resolved_stage_orders,
            resolved_special_positions,
            metal,
            theme,
            epsilon,
        ),
        "stageSummary": _build_summary(figure_nodes, figure_links),
        "stageControls": _build_stage_controls(
            visible_nodes,
            visible_links,
            resolved_sort_modes,
            resolved_stage_orders,
            resolved_special_positions,
            resolved_aggregate_counts,
        ),
        "datasetStatus": dataset_status,
        "notes": notes,
    }


__all__ = [
    "DEFAULT_SORT_MODE",
    "DEFAULT_SPECIAL_POSITION",
    "DEFAULT_THEME",
    "DEFAULT_REFERENCE_QTY",
    "SORT_MODES",
    "SPECIAL_COLORS",
    "SPECIAL_NODE_POSITIONS",
    "STAGE_LABELS",
    "STAGE_ORDER",
    "SankeyBuilder",
    "THEME_MODES",
    "VIEW_LABELS",
    "VIEW_MODES",
    "LinkSpec",
    "NodeSpec",
    "_clip",
    "_resolve_balance_adjustment",
    "_sum_maps",
    "add_country_trade_section",
    "add_shared_pool_chem_trade_section",
    "add_stage_sink_links",
    "make_payload",
    "resolve_view_mode",
    "view_mode_label",
]
