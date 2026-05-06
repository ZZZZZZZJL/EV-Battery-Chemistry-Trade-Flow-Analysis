from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Any

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
LOGGER = logging.getLogger(__name__)
S7_VIEW_MODES = ("country", "chemistry", "chemistry_only")


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


def _request_dict(request: FigureRequestModel) -> dict[str, Any]:
    if hasattr(request, "model_dump"):
        return request.model_dump()
    return request.dict()


def _public_request_json(request: FigureRequestModel, access_mode: str) -> str:
    data = _request_dict(request)
    data["accessMode"] = access_mode
    data.pop("accessPassword", None)
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _runtime_cache_version(repo: Any) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps({"metals": repo.metals, "years": repo.years}, sort_keys=True).encode("utf-8"))
    for attr in (
        "original_data_root",
        "first_optimization_data_root",
        "first_optimization_diagnostics_root",
        "version_output_root",
    ):
        root = getattr(repo, attr, None)
        try:
            exists = bool(root and root.exists())
            mtime = root.stat().st_mtime_ns if exists else 0
            digest.update(f"{attr}:{int(exists)}:{mtime}".encode("utf-8"))
        except OSError:
            digest.update(f"{attr}:unavailable".encode("utf-8"))
    return digest.hexdigest()[:16]


def _validate_request(repo: Any, request: FigureRequestModel) -> None:
    if request.metal not in repo.metals:
        raise HTTPException(status_code=400, detail=f"Unsupported metal: {request.metal}")
    if request.year not in repo.years:
        raise HTTPException(status_code=400, detail=f"Unsupported year: {request.year}")
    if request.resultMode not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unsupported result mode: {request.resultMode}")
    if request.tableView not in TABLE_VIEWS:
        raise HTTPException(status_code=400, detail=f"Unsupported table view: {request.tableView}")
    if request.s7ViewMode not in S7_VIEW_MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported S7 view mode: {request.s7ViewMode}")
    if request.referenceQuantity is not None and request.referenceQuantity <= 0:
        raise HTTPException(status_code=400, detail="Reference quantity must be positive.")


def _runtime_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Runtime data is unavailable for the requested figure.")


@lru_cache(maxsize=128)
def _build_cached_payload(cache_version: str, request_json: str) -> dict:
    data = json.loads(request_json)
    return build_sankey_payload(
        metal=data["metal"],
        year=data["year"],
        result_mode=data["resultMode"],
        table_view=data["tableView"],
        theme=data["theme"],
        reference_qty=data.get("referenceQuantity"),
        sort_modes=data.get("sortModes") or {},
        stage_orders=data.get("stageOrders") or {},
        special_positions=data.get("specialPositions") or {},
        aggregate_counts=data.get("aggregateCounts") or {},
        cobalt_mode=data.get("cobaltMode", DEFAULT_COBALT_MODE),
        access_mode=data.get("accessMode", DEFAULT_ACCESS_MODE),
        s7_view_mode=data.get("s7ViewMode", "country"),
        s7_aggregate_nmc_nca=bool(data.get("s7AggregateNmcNca", False)),
    )


def _figure_response(request: FigureRequestModel, access_mode: str) -> JSONResponse:
    started = time.perf_counter()
    try:
        repo = get_repository()
    except (FileNotFoundError, OSError) as exc:
        raise _runtime_unavailable(exc) from exc
    _validate_request(repo, request)
    request_json = _public_request_json(request, access_mode)
    cache_version = _runtime_cache_version(repo)
    try:
        payload = copy.deepcopy(_build_cached_payload(cache_version, request_json))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, OSError) as exc:
        raise _runtime_unavailable(exc) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    LOGGER.info(
        "figure payload built metal=%s year=%s result=%s access=%s elapsed_ms=%.1f cache=%s",
        request.metal,
        request.year,
        request.resultMode,
        access_mode,
        elapsed_ms,
        _build_cached_payload.cache_info(),
    )
    return JSONResponse(payload)


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
    request = FigureRequestModel(
        metal=metal,
        year=year,
        resultMode=result_mode,
        tableView=table_view,
        theme=theme,
        referenceQuantity=reference_qty,
        cobaltMode=cobalt_mode,
        accessMode=validated_access_mode,
        s7ViewMode=s7_view_mode,
        s7AggregateNmcNca=s7_aggregate_nmc_nca,
    )
    return _figure_response(request, validated_access_mode)


@router.post("/api/figure")
def figure(request: FigureRequestModel) -> JSONResponse:
    validated_access_mode = _validate_access(request.accessMode, request.accessPassword)
    return _figure_response(request, validated_access_mode)


@router.get("/assets/plotly.min.js")
def plotly_asset() -> Response:
    return Response(content=get_plotlyjs(), media_type="application/javascript")

