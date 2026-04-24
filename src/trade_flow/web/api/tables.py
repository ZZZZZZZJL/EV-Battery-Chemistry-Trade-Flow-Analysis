from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from trade_flow.web.presenters.table_presenter import build_table_payload


router = APIRouter()


@router.get("/api/tables")
def tables(
    year: int,
    metal: str,
    result_mode: str = "baseline",
    table_view: str = "compare",
    cobalt_mode: str = "mid",
    access_mode: str = "guest",
) -> JSONResponse:
    try:
        payload = build_table_payload(
            metal=metal,
            year=year,
            result_mode=result_mode,
            table_view=table_view,
            cobalt_mode=cobalt_mode,
            access_mode=access_mode,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)
