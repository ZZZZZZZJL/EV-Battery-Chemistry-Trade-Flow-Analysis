from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from plotly.offline import get_plotlyjs
from pydantic import BaseModel, Field

from trade_flow.legacy_site.config import get_battery_site_config
from trade_flow.legacy_site.services.precomputed_repository import SCENARIOS, TABLE_VIEWS, get_repository
from trade_flow.legacy_site.services.precomputed_site import DEFAULT_COBALT_MODE, DEFAULT_METAL, DEFAULT_THEME
from trade_flow.web.presenters.sankey_presenter import (
    ACCESS_MODES,
    DEFAULT_ACCESS_MODE,
    build_sankey_payload,
)


router = APIRouter()
ANALYST_PASSWORD = get_battery_site_config().analyst_password


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
    s7ViewMode: str = "country"
    s7AggregateNmcNca: bool = False


def _validate_access(access_mode: str, access_password: str) -> str:
    mode = access_mode if access_mode in ACCESS_MODES else DEFAULT_ACCESS_MODE
    if mode == "analyst" and access_password != ANALYST_PASSWORD:
        raise HTTPException(status_code=403, detail="Password required to unlock non-guest mode.")
    return mode


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
    s7_view_mode: str = "country",
    s7_aggregate_nmc_nca: bool = False,
) -> JSONResponse:
    validated_access_mode = _validate_access(access_mode, access_password)
    try:
        payload = build_sankey_payload(
            metal=metal,
            year=year,
            result_mode=result_mode,
            table_view=table_view,
            theme=theme,
            reference_qty=reference_qty,
            cobalt_mode=cobalt_mode,
            access_mode=validated_access_mode,
            s7_view_mode=s7_view_mode,
            s7_aggregate_nmc_nca=s7_aggregate_nmc_nca,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.post("/api/figure")
def figure(request: FigureRequestModel) -> JSONResponse:
    get_repository()
    if request.resultMode not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unsupported result mode: {request.resultMode}")
    if request.tableView not in TABLE_VIEWS:
        raise HTTPException(status_code=400, detail=f"Unsupported table view: {request.tableView}")
    validated_access_mode = _validate_access(request.accessMode, request.accessPassword)
    try:
        payload = build_sankey_payload(
            metal=request.metal,
            year=request.year,
            result_mode=request.resultMode,
            table_view=request.tableView,
            theme=request.theme,
            reference_qty=request.referenceQuantity,
            sort_modes=request.sortModes,
            stage_orders=request.stageOrders,
            special_positions=request.specialPositions,
            aggregate_counts=request.aggregateCounts,
            cobalt_mode=request.cobaltMode,
            access_mode=validated_access_mode,
            s7_view_mode=request.s7ViewMode,
            s7_aggregate_nmc_nca=request.s7AggregateNmcNca,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.get("/assets/plotly.min.js")
def plotly_asset() -> Response:
    return Response(content=get_plotlyjs(), media_type="application/javascript")

