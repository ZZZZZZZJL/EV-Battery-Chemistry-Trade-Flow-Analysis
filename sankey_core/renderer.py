from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import plotly.graph_objects as go

from models import EPSILON, DisplayStage, LinkSpec, NodeSpec


REGION_ORDER = ["Africa", "Asia", "Europe", "North America", "South America", "Oceania", "Antarctica", "Unknown"]
TOP_BAND_PX = 80.0
BOTTOM_BAND_PX = 80.0
GAP_PX = 22.0
PLOTLY_NODE_PAD_PX = 32
MIN_STAGE_HEIGHT_PX = 100.0
REFERENCE_NODE_HEIGHT_PX = 80.0
REFERENCE_NODE_HALF_WIDTH_PAPER = 0.008
REFERENCE_LABEL_GAP_PAPER = 0.012
STAGE_TITLE_Y_RATIO = 0.30
BODY_FONT_FAMILY = "Aptos, Segoe UI, sans-serif"
DISPLAY_FONT_FAMILY = "Georgia, Times New Roman, serif"
TITLE_TEXT_COLOR = "#20160e"
BODY_TEXT_COLOR = "#32251c"
REFERENCE_TEXT_COLOR = "#1a140f"
REFERENCE_COLOR = "#8b929a"
TRANSPARENT_COLOR = "rgba(0,0,0,0)"


def _safe_token(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in str(value))


def _aggregate_links(links: Iterable[LinkSpec]) -> list[LinkSpec]:
    grouped: dict[tuple[str, str, str], float] = defaultdict(float)
    for link in links:
        if link.value > EPSILON:
            grouped[(link.source, link.target, link.color)] += float(link.value)
    return [
        LinkSpec(source=source, target=target, value=value, color=color)
        for (source, target, color), value in grouped.items()
        if value > EPSILON
    ]


def _prune(nodes: dict[str, NodeSpec], links: list[LinkSpec]) -> tuple[dict[str, NodeSpec], list[LinkSpec]]:
    connected = {link.source for link in links} | {link.target for link in links}
    visible_nodes = {key: node for key, node in nodes.items() if key in connected}
    visible_links = [link for link in links if link.source in visible_nodes and link.target in visible_nodes]
    return visible_nodes, visible_links


def _node_values(nodes: dict[str, NodeSpec], links: list[LinkSpec]) -> dict[str, float]:
    incoming: dict[str, float] = defaultdict(float)
    outgoing: dict[str, float] = defaultdict(float)
    for link in links:
        outgoing[link.source] += link.value
        incoming[link.target] += link.value
    return {key: max(incoming.get(key, 0.0), outgoing.get(key, 0.0)) for key in nodes}


def _node_country_id(key: str) -> int | None:
    parts = str(key).split(":")
    for marker in ("country", "chem"):
        if marker not in parts:
            continue
        index = parts.index(marker) + 1
        if index >= len(parts):
            continue
        try:
            return int(parts[index])
        except ValueError:
            return None
    return None


def _is_preserved_country_node(key: str, preserved_country_ids: frozenset[int]) -> bool:
    country_id = _node_country_id(key)
    return country_id is not None and country_id in preserved_country_ids


def _region_rank(region: str) -> tuple[int, str]:
    try:
        return (REGION_ORDER.index(region), region)
    except ValueError:
        return (len(REGION_ORDER), region)


def _stage_order(
    stage: str,
    keys: list[str],
    nodes: dict[str, NodeSpec],
    values: dict[str, float],
    sort_mode: str,
) -> list[str]:
    source_special = [key for key in keys if nodes[key].kind == "source_special"]
    regular = [key for key in keys if nodes[key].kind == "regular"]
    sink_special = [key for key in keys if nodes[key].kind == "sink_special"]
    source_special.sort(key=lambda key: (-values.get(key, 0.0), nodes[key].label))
    sink_special.sort(key=lambda key: (-values.get(key, 0.0), nodes[key].label))
    if sort_mode == "continent":
        regular.sort(key=lambda key: (_region_rank(nodes[key].region), -values.get(key, 0.0), nodes[key].label))
    else:
        regular.sort(key=lambda key: (-values.get(key, 0.0), nodes[key].label))
    if source_special and not sink_special:
        return source_special + regular
    if sink_special and not source_special:
        return regular + sink_special
    return source_special + regular + sink_special


def make_figure(
    *,
    nodes: dict[str, NodeSpec],
    links: Iterable[LinkSpec],
    stages: tuple[DisplayStage, ...],
    metal: str,
    route: str,
    reference_quantity: float,
    theme: str,
    sort_mode: str,
    label_font_size: int,
    flow_transparency_threshold: float = 0.0,
    node_transparency_threshold: float = 0.0,
    preserved_country_ids: frozenset[int] = frozenset(),
) -> go.Figure:
    if reference_quantity <= 0:
        raise ValueError("REFERENCE_QUANTITY must be greater than zero.")
    if theme not in {"dark", "light"}:
        raise ValueError("THEME must be dark or light.")
    if sort_mode not in {"size", "continent"}:
        raise ValueError("SORT_MODE must be size or continent.")
    if label_font_size <= 0:
        raise ValueError("LABEL_FONT_SIZE must be greater than zero.")
    if flow_transparency_threshold < 0 or node_transparency_threshold < 0:
        raise ValueError("Transparency thresholds must be non-negative.")
    aggregated = _aggregate_links(links)
    visible_nodes, visible_links = _prune(nodes, aggregated)
    if not visible_links:
        raise ValueError("No Sankey links were generated for the selected configuration.")

    stage_keys = [stage.key for stage in stages]
    if len(stage_keys) == 1:
        x_map = {stage_keys[0]: 0.50}
    else:
        x_map = {
            stage: 0.06 + index * (0.84 / (len(stage_keys) - 1))
            for index, stage in enumerate(stage_keys)
        }
    values = _node_values(visible_nodes, visible_links)
    grouped: dict[str, list[str]] = defaultdict(list)
    for key, node in visible_nodes.items():
        grouped[node.stage].append(key)
    ordered_by_stage = {
        stage: _stage_order(stage, grouped.get(stage, []), visible_nodes, values, sort_mode)
        for stage in stage_keys
    }

    px_per_unit = REFERENCE_NODE_HEIGHT_PX / max(reference_quantity, 1.0)
    node_heights: dict[str, float] = {}
    stage_heights: dict[str, float] = {}
    for stage in stage_keys:
        total_height = 0.0
        keys = ordered_by_stage[stage]
        for index, key in enumerate(keys):
            height = values.get(key, 0.0) * px_per_unit
            node_heights[key] = height
            total_height += height
            if index < len(keys) - 1:
                total_height += GAP_PX
        stage_heights[stage] = total_height
    content_height = max(stage_heights.values(), default=0.0)
    figure_height = int(max(MIN_STAGE_HEIGHT_PX, content_height + TOP_BAND_PX + BOTTOM_BAND_PX))
    plot_height = float(figure_height - TOP_BAND_PX - BOTTOM_BAND_PX)

    ordered_keys: list[str] = []
    x_positions: list[float] = []
    y_positions: list[float] = []
    for stage in stage_keys:
        current_y = 0.0
        for key in ordered_by_stage[stage]:
            ordered_keys.append(key)
            x_positions.append(x_map[stage])
            center_y = current_y + node_heights[key] / 2.0
            y_positions.append(center_y / plot_height if plot_height > EPSILON else 0.0)
            current_y += node_heights[key] + GAP_PX

    key_to_index = {key: index for index, key in enumerate(ordered_keys)}
    hidden_node_keys = {
        key
        for key in ordered_keys
        if visible_nodes[key].kind == "regular"
        and values.get(key, 0.0) < node_transparency_threshold
        and not _is_preserved_country_node(key, preserved_country_ids)
    }

    def link_color(link: LinkSpec) -> str:
        preserved = (
            _is_preserved_country_node(link.source, preserved_country_ids)
            or _is_preserved_country_node(link.target, preserved_country_ids)
        )
        if link.value < flow_transparency_threshold and not preserved:
            return TRANSPARENT_COLOR
        return link.color
    plot_domain_top = TOP_BAND_PX / figure_height
    plot_domain_bottom = 1.0 - (BOTTOM_BAND_PX / figure_height)
    reference_bottom_px = TOP_BAND_PX + content_height
    reference_top_px = max(reference_bottom_px - REFERENCE_NODE_HEIGHT_PX, TOP_BAND_PX)
    reference_y0 = max(0.0, 1.0 - reference_bottom_px / figure_height)
    reference_y1 = min(1.0, 1.0 - reference_top_px / figure_height)
    reference_y = (reference_y0 + reference_y1) / 2.0
    reference_center_x = min(0.965, x_map[stage_keys[-1]] + 0.04)
    reference_x0 = reference_center_x - REFERENCE_NODE_HALF_WIDTH_PAPER
    reference_x1 = reference_center_x + REFERENCE_NODE_HALF_WIDTH_PAPER

    figure = go.Figure(
        go.Sankey(
            ids=[_safe_token(key) for key in ordered_keys],
            uid=_safe_token(f"{metal}-{route}"),
            arrangement="fixed",
            domain={"x": [0.0, 1.0], "y": [plot_domain_top, plot_domain_bottom]},
            node={
                "label": ["" if key in hidden_node_keys else visible_nodes[key].label for key in ordered_keys],
                "x": x_positions,
                "y": y_positions,
                "pad": PLOTLY_NODE_PAD_PX,
                "thickness": 20,
                "line": {"color": "rgba(0,0,0,0)", "width": 0},
                "color": [TRANSPARENT_COLOR if key in hidden_node_keys else visible_nodes[key].color for key in ordered_keys],
                "customdata": [
                    f"{visible_nodes[key].hover}<br>{values.get(key, 0.0):,.0f} t"
                    for key in ordered_keys
                ],
                "hovertemplate": "%{customdata}<extra></extra>",
            },
            link={
                "source": [key_to_index[link.source] for link in visible_links],
                "target": [key_to_index[link.target] for link in visible_links],
                "value": [link.value for link in visible_links],
                "color": [link_color(link) for link in visible_links],
            },
        )
    )
    figure.update_layout(
        font={"color": BODY_TEXT_COLOR, "family": BODY_FONT_FAMILY, "size": label_font_size},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        margin={"l": 6, "r": 6, "t": 8, "b": 16},
        height=figure_height,
        annotations=[
            *[
                {
                    "xref": "paper",
                    "yref": "paper",
                    "x": x_map[stage.key],
                    "y": 1 - ((TOP_BAND_PX * STAGE_TITLE_Y_RATIO) / figure_height),
                    "text": stage.label.replace("Post Trade", "Post<br>Trade"),
                    "showarrow": False,
                    "xanchor": "center",
                    "yanchor": "middle",
                    "align": "center",
                    "font": {
                        "family": DISPLAY_FONT_FAMILY,
                        "size": label_font_size,
                        "color": TITLE_TEXT_COLOR,
                    },
                }
                for stage in stages
            ],
            {
                "xref": "paper",
                "yref": "paper",
                "x": max(0.0, reference_x0 - REFERENCE_LABEL_GAP_PAPER),
                "y": reference_y,
                "text": f"Reference Node: {reference_quantity:,.0f} t",
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "middle",
                "align": "right",
                "font": {
                    "family": BODY_FONT_FAMILY,
                    "size": label_font_size,
                    "color": REFERENCE_TEXT_COLOR,
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
                "fillcolor": REFERENCE_COLOR,
                "layer": "above",
            }
        ],
    )
    return figure
