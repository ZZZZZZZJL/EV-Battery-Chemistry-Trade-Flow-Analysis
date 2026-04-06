from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from plotly.offline import get_plotlyjs
from pydantic import BaseModel, Field

from battery_7step_site.config import get_battery_site_config
from battery_7step_site.services.precomputed_repository import (
    SCENARIO_LABELS,
    SCENARIOS,
    TABLE_VIEW_LABELS,
    TABLE_VIEWS,
    get_repository,
)
from battery_7step_site.services.precomputed_site import (
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


router = APIRouter()
ANALYST_PASSWORD = get_battery_site_config().analyst_password
ACCESS_MODES = ("guest", "analyst")
DEFAULT_ACCESS_MODE = "guest"


class FigureRequestModel(BaseModel):
    year: int
    metal: str = DEFAULT_METAL
    theme: str = DEFAULT_THEME
    resultMode: str = "baseline"
    tableView: str = "auto"
    referenceQuantity: float | None = None
    sortModes: dict[str, str] = Field(default_factory=dict)
    stageOrders: dict[str, list[str]] = Field(default_factory=dict)
    specialPositions: dict[str, str] = Field(default_factory=dict)
    aggregateCounts: dict[str, int] = Field(default_factory=dict)
    cobaltMode: str = DEFAULT_COBALT_MODE
    accessMode: str = DEFAULT_ACCESS_MODE
    accessPassword: str = ""


def _validate_access(access_mode: str, access_password: str) -> str:
    mode = access_mode if access_mode in ACCESS_MODES else DEFAULT_ACCESS_MODE
    if mode == "analyst" and access_password != ANALYST_PASSWORD:
        raise HTTPException(status_code=403, detail="Password required to unlock non-guest mode.")
    return mode


@router.get("/api/bootstrap")
def bootstrap() -> dict:
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


@router.get("/api/figure")
def figure_get(
    year: int,
    metal: str = DEFAULT_METAL,
    theme: str = DEFAULT_THEME,
    result_mode: str = "baseline",
    table_view: str = "auto",
    reference_qty: float | None = None,
    cobalt_mode: str = DEFAULT_COBALT_MODE,
    access_mode: str = DEFAULT_ACCESS_MODE,
    access_password: str = "",
) -> JSONResponse:
    repo = get_repository()
    validated_access_mode = _validate_access(access_mode, access_password)
    try:
        payload = build_app_payload(
            repo,
            metal,
            year,
            result_mode,
            table_view,
            reference_qty=reference_qty if reference_qty is not None else default_reference_quantity_for_metal(metal),
            theme=theme,
            cobalt_mode=cobalt_mode,
            access_mode=validated_access_mode,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.post("/api/figure")
def figure(request: FigureRequestModel) -> JSONResponse:
    repo = get_repository()
    if request.resultMode not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unsupported result mode: {request.resultMode}")
    if request.tableView not in TABLE_VIEWS:
        raise HTTPException(status_code=400, detail=f"Unsupported table view: {request.tableView}")
    validated_access_mode = _validate_access(request.accessMode, request.accessPassword)
    try:
        payload = build_app_payload(
            repo,
            request.metal,
            request.year,
            request.resultMode,
            request.tableView,
            reference_qty=request.referenceQuantity if request.referenceQuantity is not None else default_reference_quantity_for_metal(request.metal),
            theme=request.theme,
            sort_modes=request.sortModes,
            stage_orders=request.stageOrders,
            special_positions=request.specialPositions,
            aggregate_counts=request.aggregateCounts,
            cobalt_mode=request.cobaltMode,
            access_mode=validated_access_mode,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.get("/assets/plotly.min.js")
def plotly_asset() -> Response:
    return Response(content=get_plotlyjs(), media_type="application/javascript")
