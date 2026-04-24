from __future__ import annotations

from typing import Any

from trade_flow.legacy_site.services import cobalt_sankey, lithium_sankey, nickel_sankey
from trade_flow.legacy_site.services.cobalt_data import (
    COBALT_MODE_LABELS,
    COBALT_MODES,
    DEFAULT_COBALT_MODE,
)
from trade_flow.legacy_site.services.shared_sankey import (
    DEFAULT_SPECIAL_POSITION,
    DEFAULT_THEME,
    DEFAULT_REFERENCE_QTY,
    SPECIAL_NODE_POSITIONS,
    SORT_MODES,
    STAGE_LABELS,
    STAGE_ORDER,
    THEME_MODES,
    VIEW_LABELS,
    VIEW_MODES,
)


METALS = ["Ni", "Li", "Co", "Mn"]
AVAILABLE_METALS = ["Ni", "Li", "Co"]
DEFAULT_METAL = "Ni"
METAL_LABELS = {
    "Ni": "Nickel",
    "Li": "Lithium",
    "Co": "Cobalt",
    "Mn": "Manganese",
}


def resolve_metal(metal: str) -> str:
    normalized = str(metal).strip().title()
    if normalized not in METALS:
        raise ValueError(f"Unsupported metal: {metal}")
    return normalized


def build_app_payload(
    metal: str,
    year: int,
    view_mode: str,
    reference_qty: float = DEFAULT_REFERENCE_QTY,
    sort_modes: dict[str, str] | None = None,
    stage_orders: dict[str, list[str]] | None = None,
    special_positions: dict[str, str] | None = None,
    aggregate_counts: dict[str, int] | None = None,
    theme: str = DEFAULT_THEME,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
) -> dict[str, Any]:
    resolved_metal = resolve_metal(metal)
    if resolved_metal not in AVAILABLE_METALS:
        raise ValueError(f"{resolved_metal} data are not available yet.")
    if resolved_metal == "Ni":
        return nickel_sankey.build_app_payload(
            year,
            view_mode,
            reference_qty,
            sort_modes,
            stage_orders,
            special_positions,
            aggregate_counts,
            theme,
        )
    if resolved_metal == "Li":
        return lithium_sankey.build_app_payload(
            year,
            view_mode,
            reference_qty,
            sort_modes,
            stage_orders,
            special_positions,
            aggregate_counts,
            theme,
        )
    if resolved_metal == "Co":
        return cobalt_sankey.build_app_payload(
            year,
            view_mode,
            reference_qty,
            sort_modes,
            stage_orders,
            special_positions,
            aggregate_counts,
            theme,
            cobalt_mode,
        )
    raise ValueError(f"Unsupported metal: {metal}")


__all__ = [
    "AVAILABLE_METALS",
    "COBALT_MODE_LABELS",
    "COBALT_MODES",
    "DEFAULT_METAL",
    "DEFAULT_SPECIAL_POSITION",
    "DEFAULT_COBALT_MODE",
    "DEFAULT_THEME",
    "DEFAULT_REFERENCE_QTY",
    "METALS",
    "METAL_LABELS",
    "SPECIAL_NODE_POSITIONS",
    "SORT_MODES",
    "STAGE_LABELS",
    "STAGE_ORDER",
    "THEME_MODES",
    "VIEW_LABELS",
    "VIEW_MODES",
    "build_app_payload",
    "resolve_metal",
]

