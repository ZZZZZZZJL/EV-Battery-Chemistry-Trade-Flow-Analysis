from __future__ import annotations

import re
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from . import settings


SHEET_PATTERN = re.compile(
    r"^(lithium|cobalt|nickel|manganese)_(mining|processing|refining|pro_ref|pcam|cathode|battery)$",
    re.IGNORECASE,
)
METAL_KEYS = {"lithium": "Li", "cobalt": "Co", "nickel": "Ni", "manganese": "Mn"}
BASE_REQUIRED_COLUMNS = {"id", "reporterdesc", "status"}
PRODUCT_REQUIRED_STAGES = {"cathode", "battery"}
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def validate_session_id(value: str) -> str:
    session_id = str(value or "").strip()
    if not SESSION_PATTERN.fullmatch(session_id):
        raise ValueError("Invalid browser session id.")
    return session_id


def session_storage_key(session_id: str) -> str:
    validated = validate_session_id(session_id)
    return hashlib.sha256(validated.encode("utf-8")).hexdigest()[:12]


def inspect_workbook(path: Path, source_key: str, label: str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Production workbook does not exist: {path}")
    coverage: dict[str, dict[str, dict[str, Any]]] = {}
    workbook_statuses: set[str] = set()
    workbook_years: set[int] = set()
    with pd.ExcelFile(path) as excel:
        for sheet_name in excel.sheet_names:
            match = SHEET_PATTERN.fullmatch(sheet_name.strip())
            if match is None:
                continue
            frame = pd.read_excel(excel, sheet_name=sheet_name)
            normalized_columns = {str(column).strip().casefold() for column in frame.columns}
            stage = match.group(2).casefold()
            required_columns = set(BASE_REQUIRED_COLUMNS)
            if stage in PRODUCT_REQUIRED_STAGES:
                required_columns.add("product")
            missing = sorted(required_columns - normalized_columns)
            if missing:
                raise ValueError(
                    f"Workbook {path.name}, sheet={sheet_name} is missing columns: {missing}"
                )
            metal = METAL_KEYS[match.group(1).casefold()]
            years = sorted(
                {
                    int(column)
                    for column in frame.columns
                    if str(column).strip().isdigit() and 1900 <= int(column) <= 2200
                }
            )
            status_column = next(
                column for column in frame.columns if str(column).strip().casefold() == "status"
            )
            statuses = sorted(
                {
                    str(value).strip()
                    for value in frame[status_column].dropna()
                    if str(value).strip()
                },
                key=str.casefold,
            )
            workbook_statuses.update(statuses)
            workbook_years.update(years)
            coverage.setdefault(metal, {})[stage] = {
                "sheet": sheet_name,
                "years": years,
                "statuses": statuses,
                "rows": int(len(frame)),
            }
    if not coverage:
        raise ValueError(
            "No supported production sheets were found. Expected names such as nickel_mining."
        )
    return {
        "key": source_key,
        "label": label,
        "fileName": path.name,
        "path": str(path),
        "coverage": coverage,
        "metals": [metal for metal in settings.SUPPORTED_METALS if metal in coverage],
        "years": sorted(workbook_years),
        "statuses": sorted(workbook_statuses, key=str.casefold),
        "sheetCount": sum(len(stages) for stages in coverage.values()),
    }


def upload_path(session_id: str, source_key: str) -> Path:
    session_key = session_storage_key(session_id)
    if source_key not in settings.UPLOAD_SOURCE_KEYS:
        raise ValueError(f"{source_key!r} is not an upload-backed source.")
    return settings.UPLOAD_ROOT / session_key / f"{source_key}.xlsx"


def source_paths(session_id: str) -> dict[str, Path | None]:
    session_id = validate_session_id(session_id)
    paths: dict[str, Path | None] = {}
    for source_key, definition in settings.SOURCE_DEFINITIONS.items():
        if definition["uploadRequired"]:
            candidate = upload_path(session_id, source_key)
            paths[source_key] = candidate if candidate.exists() else None
        else:
            paths[source_key] = Path(definition["path"])
    return paths


def source_catalog(session_id: str) -> list[dict[str, Any]]:
    paths = source_paths(session_id)
    catalog: list[dict[str, Any]] = []
    for source_key, definition in settings.SOURCE_DEFINITIONS.items():
        path = paths[source_key]
        base = {
            "key": source_key,
            "label": definition["label"],
            "description": definition["description"],
            "uploadRequired": bool(definition["uploadRequired"]),
            "allStatusOnly": bool(definition["allStatusOnly"]),
            "available": bool(path and path.exists()),
        }
        if path and path.exists():
            base.update(inspect_workbook(path, source_key, definition["label"]))
        else:
            base.update({"coverage": {}, "metals": [], "years": [], "statuses": [], "sheetCount": 0})
        catalog.append(base)
    return catalog


def available_trade_years() -> list[int]:
    years: list[int] = []
    pattern = re.compile(r"^UNComtrade_(\d{4})_Import_ByPartner$")
    if not settings.TRADE_ROOT.exists():
        return years
    for child in settings.TRADE_ROOT.iterdir():
        match = pattern.fullmatch(child.name) if child.is_dir() else None
        if match:
            years.append(int(match.group(1)))
    return sorted(set(years))


def reference_countries() -> list[dict[str, Any]]:
    if not settings.REFERENCE_FILE.exists():
        raise FileNotFoundError(f"Reference workbook does not exist: {settings.REFERENCE_FILE}")
    frame = pd.read_excel(settings.REFERENCE_FILE)
    if "id" not in frame.columns:
        raise ValueError("Reference workbook is missing the id column.")
    name_column = "text" if "text" in frame.columns else "reporterDesc"
    iso3_column = "reporterCodeIsoAlpha3" if "reporterCodeIsoAlpha3" in frame.columns else None
    countries: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        try:
            country_id = int(row["id"])
        except (TypeError, ValueError):
            continue
        name = str(row.get(name_column, "")).strip()
        iso3 = str(row.get(iso3_column, "")).strip() if iso3_column else ""
        if not name or name.casefold() == "nan":
            continue
        if iso3.casefold() == "nan":
            iso3 = ""
        countries.append({"id": country_id, "name": name, "iso3": iso3})
    return sorted(countries, key=lambda item: item["name"].casefold())
