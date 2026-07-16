from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from . import settings
from .generation import active_route, generate
from .inventory import (
    available_trade_years,
    inspect_workbook,
    reference_countries,
    session_storage_key,
    source_catalog,
    upload_path,
    validate_session_id,
)


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _artifact_urls(session_id: str, outputs: dict[str, str]) -> dict[str, str]:
    run_directory = Path(outputs["run_directory"])
    run_id = run_directory.name
    return {
        key: f"/artifacts/{session_id}/{run_id}/{Path(path).name}"
        for key, path in outputs.items()
        if key != "run_directory"
    }


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(MAX_CONTENT_LENGTH=settings.MAX_UPLOAD_BYTES)
    if test_config:
        app.config.update(test_config)
    settings.UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    settings.ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/bootstrap")
    def bootstrap():
        try:
            session_id = validate_session_id(request.args.get("sessionId", ""))
            sources = source_catalog(session_id)
            route = active_route({"mergeProcessingRefining": False, "showPcam": True, "showBattery": True})
            return jsonify(
                {
                    "ok": True,
                    "sessionId": session_id,
                    "tradeYears": available_trade_years(),
                    "sources": sources,
                    "countries": reference_countries(),
                    "defaultRoute": route,
                    "defaults": {
                        "metal": "Ni",
                        "year": 2024,
                        "referenceQuantity": 700000,
                        "labelFontSize": 16,
                    },
                }
            )
        except (ValueError, FileNotFoundError, OSError) as exc:
            return _json_error(str(exc))

    @app.post("/api/uploads/<source_key>")
    def upload(source_key: str):
        if source_key not in settings.UPLOAD_SOURCE_KEYS:
            return _json_error("Only SCInsight and Benchmark are upload-backed sources.")
        try:
            session_id = validate_session_id(request.form.get("sessionId", ""))
            file = request.files.get("file")
            if file is None or not file.filename:
                raise ValueError("Choose an .xlsx production workbook.")
            if Path(secure_filename(file.filename)).suffix.casefold() != ".xlsx":
                raise ValueError("Production uploads must use the .xlsx format.")
            destination = upload_path(session_id, source_key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.stem}.uploading.xlsx")
            file.save(temporary)
            if temporary.stat().st_size > settings.MAX_UPLOAD_BYTES:
                temporary.unlink(missing_ok=True)
                raise ValueError("The uploaded workbook exceeds the 20 MB limit.")
            try:
                inventory = inspect_workbook(
                    temporary,
                    source_key,
                    settings.SOURCE_DEFINITIONS[source_key]["label"],
                )
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            temporary.replace(destination)
            inventory["path"] = str(destination)
            return jsonify({"ok": True, "source": inventory, "sources": source_catalog(session_id)})
        except (ValueError, FileNotFoundError, OSError) as exc:
            return _json_error(str(exc))

    @app.delete("/api/uploads/<source_key>")
    def remove_upload(source_key: str):
        try:
            session_id = validate_session_id(request.args.get("sessionId", ""))
            path = upload_path(session_id, source_key)
            path.unlink(missing_ok=True)
            return jsonify({"ok": True, "sources": source_catalog(session_id)})
        except (ValueError, OSError) as exc:
            return _json_error(str(exc))

    @app.post("/api/route")
    def route_preview():
        try:
            return jsonify({"ok": True, "route": active_route(request.get_json(silent=True) or {})})
        except (ValueError, FileNotFoundError) as exc:
            return _json_error(str(exc))

    @app.post("/api/generate")
    def generate_figure():
        payload = request.get_json(silent=True) or {}
        try:
            session_id = validate_session_id(payload.get("sessionId", ""))
            started = time.perf_counter()
            result = generate(payload, session_id)
            urls = _artifact_urls(session_id, result["outputs"])
            return jsonify(
                {
                    "ok": True,
                    "route": result["route"],
                    "manifest": result["manifest"],
                    "artifacts": urls,
                    "elapsedSeconds": round(time.perf_counter() - started, 2),
                }
            )
        except (ValueError, FileNotFoundError, RuntimeError, OSError, KeyError) as exc:
            return _json_error(str(exc))

    @app.get("/artifacts/<session_id>/<run_id>/<path:filename>")
    def artifact(session_id: str, run_id: str, filename: str):
        try:
            session_id = validate_session_id(session_id)
            if Path(run_id).name != run_id or Path(filename).name != filename:
                raise ValueError("Invalid artifact path.")
            directory = settings.ARTIFACT_ROOT / session_storage_key(session_id) / run_id
            return send_from_directory(
                directory,
                filename,
                as_attachment=request.args.get("download") == "1",
            )
        except (ValueError, FileNotFoundError) as exc:
            return _json_error(str(exc), 404)

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    return app
