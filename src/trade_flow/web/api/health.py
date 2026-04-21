from __future__ import annotations

from fastapi.responses import JSONResponse


def build_health_response(payload: dict, ready: bool) -> JSONResponse:
    return JSONResponse(payload, status_code=200 if ready else 503)
