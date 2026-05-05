from __future__ import annotations

from trade_flow.legacy_site.services.precomputed_repository import (
    SCENARIO_LABELS,
    TABLE_VIEW_LABELS,
    TABLE_VIEWS,
    get_repository,
)
from trade_flow.legacy_site.services.precomputed_site import (
    COBALT_MODE_LABELS,
    COBALT_MODES,
    DEFAULT_COBALT_MODE,
    DEFAULT_METAL,
    DEFAULT_REFERENCE_QTY,
    DEFAULT_REFERENCE_QTY_BY_METAL,
    DEFAULT_SPECIAL_POSITION,
    DEFAULT_THEME,
    RESULT_MODES,
    SORT_MODES,
    SPECIAL_NODE_POSITIONS,
    STAGE_LABELS,
    STAGE_ORDER,
    THEME_MODES,
    build_app_payload,
    default_reference_quantity_for_metal,
)


ACCESS_MODES = ("guest", "analyst")
DEFAULT_ACCESS_MODE = "guest"


def build_bootstrap_payload() -> dict:
    repo = get_repository()
    return {
        "metadata": {
            "metals": [{"id": metal, "label": metal, "available": metal in repo.metals} for metal in repo.metals],
            "defaultMetal": DEFAULT_METAL if DEFAULT_METAL in repo.metals else repo.metals[0],
            "themes": list(THEME_MODES),
            "defaultTheme": DEFAULT_THEME,
            "years": repo.years,
            "defaultYear": max(repo.years),
            "resultModes": list(RESULT_MODES),
            "resultLabels": SCENARIO_LABELS,
            "tableViews": list(TABLE_VIEWS),
            "tableViewLabels": TABLE_VIEW_LABELS,
            "cobaltModes": list(COBALT_MODES),
            "cobaltModeLabels": COBALT_MODE_LABELS,
            "defaultCobaltMode": DEFAULT_COBALT_MODE,
            "stageLabels": STAGE_LABELS,
            "stageOrder": STAGE_ORDER,
            "sortModes": list(SORT_MODES),
            "specialNodePositions": list(SPECIAL_NODE_POSITIONS),
            "defaultSpecialNodePosition": DEFAULT_SPECIAL_POSITION,
            "defaultReferenceQuantity": DEFAULT_REFERENCE_QTY,
            "defaultReferenceQuantities": DEFAULT_REFERENCE_QTY_BY_METAL,
            "defaultAccessMode": DEFAULT_ACCESS_MODE,
        }
    }


def build_sankey_payload(
    *,
    metal: str,
    year: int,
    result_mode: str,
    table_view: str,
    theme: str,
    reference_qty: float | None,
    sort_modes: dict[str, str] | None = None,
    stage_orders: dict[str, list[str]] | None = None,
    special_positions: dict[str, str] | None = None,
    aggregate_counts: dict[str, int] | None = None,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
    access_mode: str = DEFAULT_ACCESS_MODE,
    s7_view_mode: str = "country",
    s7_aggregate_nmc_nca: bool = False,
) -> dict:
    repo = get_repository()
    return build_app_payload(
        repo,
        metal,
        year,
        result_mode,
        table_view,
        reference_qty=reference_qty if reference_qty is not None else default_reference_quantity_for_metal(metal),
        theme=theme,
        sort_modes=sort_modes or {},
        stage_orders=stage_orders or {},
        special_positions=special_positions or {},
        aggregate_counts=aggregate_counts or {},
        cobalt_mode=cobalt_mode,
        access_mode=access_mode,
        s7_view_mode=s7_view_mode,
        s7_aggregate_nmc_nca=s7_aggregate_nmc_nca,
    )

