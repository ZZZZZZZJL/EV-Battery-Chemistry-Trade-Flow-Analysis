from __future__ import annotations

from fastapi import APIRouter

from trade_flow.web.presenters.sankey_presenter import build_bootstrap_payload


router = APIRouter()


@router.get("/api/bootstrap")
def bootstrap() -> dict:
    return build_bootstrap_payload()
