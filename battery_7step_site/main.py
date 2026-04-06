from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from battery_7step_site.api.routes import router
from battery_7step_site.config import get_battery_site_config
from battery_7step_site.services.runtime_checks import RuntimeStatus, gather_runtime_status


site_config = get_battery_site_config()
app = FastAPI(title="Battery Metals 7-Step Flow Atlas")
app.mount("/static", StaticFiles(directory=str(site_config.static_dir)), name="static")
templates = Jinja2Templates(directory=str(site_config.templates_dir))
app.include_router(router)


def _runtime_status() -> RuntimeStatus:
    status = getattr(app.state, "runtime_status", None)
    if status is None:
        status = gather_runtime_status(site_config)
        app.state.runtime_status = status
    return status


@app.on_event("startup")
def startup_runtime_validation() -> None:
    status = gather_runtime_status(site_config)
    app.state.runtime_status = status
    if site_config.strict_startup and not status.ready:
        raise RuntimeError("; ".join(status.errors))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/healthz")
def healthz() -> JSONResponse:
    status = _runtime_status()
    return JSONResponse(status.to_public_dict(), status_code=200 if status.ready else 503)
