from __future__ import annotations

import math
from colorsys import hls_to_rgb
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from models import EPSILON, ProductionData, ReferenceMaps, RouteSpec, Settings, TradeRecord


METAL_PREFIXES = {"Li": "lithium", "Co": "cobalt", "Ni": "nickel", "Mn": "manganese"}
REGION_COLORS = {
    "Africa": "#800080",
    "Europe": "#008000",
    "Asia": "#FFA500",
    "North America": "#b38f00",
    "South America": "#FF0000",
    "Oceania": "#0000FF",
    "Antarctica": "#000000",
    "Unknown": "#7f8c8d",
}


def normalize_metal(value: str) -> str:
    aliases = {
        "li": "Li",
        "lithium": "Li",
        "co": "Co",
        "cobalt": "Co",
        "ni": "Ni",
        "nickel": "Ni",
        "mn": "Mn",
        "manganese": "Mn",
    }
    try:
        return aliases[str(value).strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported metal {value!r}. Choose Li, Co, Ni, or Mn.") from exc


def _normalize_color(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    color = str(value).strip().lstrip("#").upper()
    if len(color) == 3:
        color = "".join(character * 2 for character in color)
    if len(color) != 6 or any(character not in "0123456789ABCDEF" for character in color):
        return None
    return f"#{color}"


def _clean_text(value: Any, fallback: str) -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    return text or fallback


def _hsl_to_hex(hue: float, saturation: float, lightness: float) -> str:
    red, green, blue = hls_to_rgb(hue, lightness, saturation)
    return "#%02x%02x%02x" % (int(red * 255), int(green * 255), int(blue * 255))


def load_reference(path: Path, required_ids: set[int] | None = None) -> ReferenceMaps:
    if not path.exists():
        raise FileNotFoundError(f"Reference workbook does not exist: {path}")
    frame = pd.read_excel(path)
    if "id" not in frame.columns:
        raise ValueError(f"Reference workbook is missing the id column: {path}")
    name_column = "text" if "text" in frame.columns else "reporterDesc"
    iso3_column = "reporterCodeIsoAlpha3" if "reporterCodeIsoAlpha3" in frame.columns else None
    names: dict[int, str] = {}
    iso3: dict[int, str] = {}
    colors: dict[int, str] = {}
    regions: dict[int, str] = {}
    for _, row in frame.iterrows():
        try:
            country_id = int(row["id"])
        except (TypeError, ValueError):
            continue
        names[country_id] = _clean_text(row.get(name_column), str(country_id))
        iso3[country_id] = _clean_text(row.get(iso3_column), "") if iso3_column else ""
        region = _clean_text(row.get("region"), "Unknown")
        regions[country_id] = region
        color = _normalize_color(row.get("color"))
        if color:
            colors[country_id] = color

    missing = sorted(set(required_ids or ()) - set(colors))
    used = {color.upper() for color in colors.values()}
    for index, country_id in enumerate(missing):
        hue = (index * 0.618033988749895) % 1.0
        saturation = min(0.58 + (index % 3) * 0.08, 0.82)
        lightness = min(0.4 + ((index // 3) % 3) * 0.06, 0.62)
        candidate = _hsl_to_hex(hue, saturation, lightness)
        while candidate.upper() in used:
            hue = (hue + 0.073) % 1.0
            candidate = _hsl_to_hex(hue, saturation, lightness)
        colors[country_id] = candidate
        used.add(candidate.upper())
    for country_id in set(required_ids or ()):
        names.setdefault(country_id, f"Country {country_id}")
        iso3.setdefault(country_id, "")
        regions.setdefault(country_id, "Unknown")
        colors.setdefault(country_id, REGION_COLORS["Unknown"])
    return ReferenceMaps(names=names, iso3=iso3, colors=colors, regions=regions)


def _year_column(frame: pd.DataFrame, year: int) -> Any:
    for column in frame.columns:
        try:
            if int(column) == int(year):
                return column
        except (TypeError, ValueError):
            continue
    raise ValueError(f"Production workbook does not contain year {year}.")


def _stage_totals(frame: pd.DataFrame, year_column: Any, path: Path) -> pd.DataFrame:
    selected = frame.copy()
    if "Product" in selected.columns:
        product = selected["Product"].fillna("").astype(str).str.strip().str.lower()
        if product.eq("total").any():
            selected = selected.loc[product.eq("total")].copy()
        # Some SCInsight stages contain only product-detail rows (for example,
        # cobalt refining uses "sulphate"). In that schema the country total is
        # the sum of all detail products, so retain them for the group-by below.
    selected["id"] = pd.to_numeric(selected["id"], errors="coerce")
    selected[year_column] = pd.to_numeric(selected[year_column], errors="coerce").fillna(0.0)
    return selected


def _normalize_production_frame(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {}
    if "Desc" not in frame.columns and "reporterDesc" in frame.columns:
        aliases["reporterDesc"] = "Desc"
    if "Product" not in frame.columns and "product" in frame.columns:
        aliases["product"] = "Product"
    if "status" not in frame.columns and "Status" in frame.columns:
        aliases["Status"] = "status"
    return frame.rename(columns=aliases)


def _read_legacy_production_workbook(
    path: Path,
    requested_sheets: tuple[str, ...] | None,
    settings: Settings,
    route: RouteSpec,
    stage_key: str,
    production_source: str,
) -> dict[str, pd.DataFrame]:
    """Read the former one-workbook-per-stage schema."""
    with pd.ExcelFile(path) as excel:
        available = excel.sheet_names
        if not available:
            raise ValueError(f"Production workbook has no worksheets: {path}")
        if requested_sheets is None:
            selected_names = available
        else:
            by_normalized = {name.strip().casefold(): name for name in available}
            missing = [name for name in requested_sheets if name.strip().casefold() not in by_normalized]
            if missing:
                raise ValueError(
                    "Missing production sheet(s): "
                    f"source={production_source}, metal={settings.metal}, "
                    f"route={route.key}, stage={stage_key}, file={path}, "
                    f"requested={missing}, available={available}"
                )
            selected_names = [by_normalized[name.strip().casefold()] for name in requested_sheets]
        frames = pd.read_excel(excel, sheet_name=selected_names)
    return {name: _normalize_production_frame(frame) for name, frame in frames.items()}


def _read_consolidated_production_stage(
    path: Path,
    stage_sheet: str,
    requested_statuses: tuple[str, ...] | None,
    settings: Settings,
    route: RouteSpec,
    stage_key: str,
    production_source: str,
) -> dict[str, pd.DataFrame]:
    """Read one metal/stage sheet and split it into the requested status rows."""
    with pd.ExcelFile(path) as excel:
        available_sheets = excel.sheet_names
        by_normalized_sheet = {name.strip().casefold(): name for name in available_sheets}
        actual_sheet = by_normalized_sheet.get(stage_sheet.casefold())
        if actual_sheet is None:
            raise FileNotFoundError(
                "Missing production-stage sheet: "
                f"source={production_source}, metal={settings.metal}, route={route.key}, "
                f"stage={stage_key}, workbook={path}, expected_sheet={stage_sheet}, "
                f"available={available_sheets}"
            )
        frame = _normalize_production_frame(pd.read_excel(excel, sheet_name=actual_sheet))

    if "status" not in frame.columns:
        raise ValueError(
            f"Production workbook {path}, sheet={actual_sheet} is missing the status column."
        )
    status_text = frame["status"].fillna("").astype(str).str.strip()
    available_statuses = list(dict.fromkeys(status for status in status_text if status))
    by_normalized_status = {status.casefold(): status for status in available_statuses}
    if requested_statuses is None:
        selected_statuses = available_statuses
    else:
        missing = [
            status for status in requested_statuses
            if status.strip().casefold() not in by_normalized_status
        ]
        if missing:
            raise ValueError(
                "Missing production status(es): "
                f"source={production_source}, metal={settings.metal}, route={route.key}, "
                f"stage={stage_key}, workbook={path}, sheet={actual_sheet}, "
                f"requested={missing}, available={available_statuses}"
            )
        selected_statuses = [
            by_normalized_status[status.strip().casefold()] for status in requested_statuses
        ]
    return {
        status: frame.loc[status_text.str.casefold().eq(status.casefold())].copy()
        for status in selected_statuses
    }


def load_production(settings: Settings, route: RouteSpec) -> ProductionData:
    prefix = METAL_PREFIXES[settings.metal]
    source_by_stage = settings.production_sources_by_stage or {
        stage.key: settings.production_source for stage in route.production_stages
    }
    production_roots = settings.production_roots or {
        settings.production_source: settings.production_root
    }
    totals: dict[str, dict[int, float]] = {}
    labels: dict[int, str] = {}
    chemistry: dict[str, dict[int, float]] = {}
    stage_chemistry: dict[str, dict[str, dict[int, float]]] = {}
    ignored_rows: list[dict[str, Any]] = []
    sheet_summary_rows: list[dict[str, Any]] = []

    for stage in route.production_stages:
        if stage.key not in source_by_stage:
            raise ValueError(
                f"No production source configured for active route stage={stage.key}."
            )
        production_source = source_by_stage[stage.key]
        if production_source not in production_roots:
            raise ValueError(
                f"Unknown production source={production_source!r} for stage={stage.key}."
            )
        source_path = production_roots[production_source]
        if not source_path.exists():
            raise FileNotFoundError(
                "Production source path does not exist: "
                f"source={production_source}, stage={stage.key}, path={source_path}"
            )
        requested_statuses = (
            ("all",)
            if production_source in settings.production_all_status_sources
            else settings.production_sheets
        )
        stage_sheet = f"{prefix}_{stage.key}"
        if source_path.is_file():
            path = source_path
            sheet_frames = _read_consolidated_production_stage(
                path,
                stage_sheet,
                requested_statuses,
                settings,
                route,
                stage.key,
                production_source,
            )
        elif source_path.is_dir():
            path = source_path / f"{stage_sheet}.xlsx"
            if not path.exists():
                raise FileNotFoundError(
                    "Missing production-stage workbook: "
                    f"source={production_source}, metal={settings.metal}, route={route.key}, "
                    f"stage={stage.key}, path={path}"
                )
            sheet_frames = _read_legacy_production_workbook(
                path,
                requested_statuses,
                settings,
                route,
                stage.key,
                production_source,
            )
        else:
            raise ValueError(
                f"Production source is neither a workbook nor a directory: {source_path}"
            )
        selected_parts: list[pd.DataFrame] = []
        chemistry_parts: list[pd.DataFrame] = []
        for sheet_name, frame in sheet_frames.items():
            required = {"id", "Desc"}
            missing_columns = sorted(required - set(frame.columns))
            if missing_columns:
                raise ValueError(
                    f"Production workbook {path}, sheet={sheet_name} is missing columns: {missing_columns}"
                )
            year_column = _year_column(frame, settings.year)
            numeric_ids = pd.to_numeric(frame["id"], errors="coerce")
            for _, row in frame.loc[numeric_ids.isna()].iterrows():
                ignored_rows.append(
                    {
                        "stage": stage.key,
                        "file": str(path),
                        "sheet": sheet_name,
                        "description": str(row.get("Desc") or "").strip(),
                        "reason": "missing id; ignored by user instruction",
                    }
                )
            for _, row in frame.loc[numeric_ids.notna(), ["id", "Desc"]].drop_duplicates().iterrows():
                labels.setdefault(int(row["id"]), _clean_text(row["Desc"], str(int(row["id"]))))

            selected = _stage_totals(frame, year_column, path)
            selected = selected.rename(columns={year_column: "_production_value"})
            selected_parts.append(selected)
            sheet_summary_rows.append(
                {
                    "production_source": production_source,
                    "metal": settings.metal,
                    "year": settings.year,
                    "route": route.key,
                    "stage": stage.key,
                    "workbook": str(path),
                    "stage_sheet": stage_sheet,
                    "sheet": sheet_name,
                    "row_count": len(frame),
                    "selected_year_total": float(selected["_production_value"].sum()),
                }
            )
            detail = frame.copy().rename(columns={year_column: "_production_value"})
            chemistry_parts.append(detail)

        combined = pd.concat(selected_parts, ignore_index=True, sort=False)
        grouped = combined.dropna(subset=["id"]).groupby("id", as_index=False)["_production_value"].sum()
        totals[stage.key] = {
            int(row["id"]): float(row["_production_value"])
            for _, row in grouped.iterrows()
            if float(row["_production_value"]) > EPSILON
        }

        if stage.key in {"cathode", "battery"}:
            detail = pd.concat(chemistry_parts, ignore_index=True, sort=False)
            if "Product" not in detail.columns:
                raise ValueError(f"Cathode chemistry view requires a Product column: {path}")
            detail["id"] = pd.to_numeric(detail["id"], errors="coerce")
            detail["_production_value"] = pd.to_numeric(
                detail["_production_value"], errors="coerce"
            ).fillna(0.0)
            product = detail["Product"].fillna("").astype(str).str.strip()
            detail = detail.loc[detail["id"].notna() & product.ne("") & product.str.lower().ne("total")].copy()
            detail["Product"] = product.loc[detail.index]
            if settings.metal == "Li" and stage.key == "cathode":
                # SCInsight provides two parallel descriptions of the same Li
                # cathode volume: salt form and battery chemistry. Only the
                # battery-chemistry dimension may be summed to Product=Total.
                battery_chemistries = {"LFP", "LMFP", "NMC", "NCM", "NCA"}
                detail = detail.loc[detail["Product"].str.upper().isin(battery_chemistries)].copy()
            stage_products: dict[str, dict[int, float]] = {}
            if settings.merge_lmfp_into_lfp:
                detail.loc[detail["Product"].str.upper().eq("LMFP"), "Product"] = "LFP"
            for product_name, product_frame in detail.groupby("Product"):
                product_grouped = product_frame.groupby("id", as_index=False)["_production_value"].sum()
                product_values = {
                    int(row["id"]): float(row["_production_value"])
                    for _, row in product_grouped.iterrows()
                    if float(row["_production_value"]) > EPSILON
                }
                stage_products[str(product_name).strip().upper()] = product_values
                if stage.key == "cathode":
                    chemistry[str(product_name).strip().upper()] = product_values
            stage_chemistry[stage.key] = stage_products

    return ProductionData(
        totals=totals,
        labels=labels,
        cathode_chemistry=chemistry,
        stage_chemistry=stage_chemistry,
        ignored_rows=tuple(ignored_rows),
        sheet_summary_rows=tuple(sheet_summary_rows),
    )


def _quantity_to_tonnes(frame: pd.DataFrame) -> pd.Series:
    if "qtyUnitAbbr" in frame.columns and "qty" in frame.columns:
        quantity = pd.to_numeric(frame["qty"], errors="coerce")
        unit = frame["qtyUnitAbbr"].fillna("").astype(str).str.strip().str.lower()
        tonnes = pd.Series(float("nan"), index=frame.index, dtype=float)
        tonnes.loc[unit.eq("kg")] = quantity.loc[unit.eq("kg")] / 1000.0
        tonnes.loc[unit.isin({"t", "ton", "tonne", "tonnes"})] = quantity.loc[
            unit.isin({"t", "ton", "tonne", "tonnes"})
        ]
        if tonnes.notna().any():
            return tonnes.fillna(0.0)
    if "netWgt" in frame.columns:
        return pd.to_numeric(frame["netWgt"], errors="coerce").fillna(0.0) / 1000.0
    raise ValueError("Raw trade file is missing usable qty/qtyUnitAbbr and netWgt columns.")


def load_trade_records(settings: Settings, transition_key: str) -> list[TradeRecord]:
    hs_mapping = settings.post_trade_hs.get(transition_key, {})
    if not hs_mapping:
        return []
    year_root = settings.trade_root / f"UNComtrade_{settings.year}_Import_ByPartner"
    if not year_root.exists():
        raise FileNotFoundError(f"Raw import folder does not exist: {year_root}")
    aggregated: dict[tuple[str, int, int], dict[str, Any]] = defaultdict(
        lambda: {"quantity": 0.0, "files": []}
    )
    for raw_hs_code, raw_factor in hs_mapping.items():
        hs_code = str(raw_hs_code).strip()
        if not hs_code:
            raise ValueError(f"Blank HS code in {transition_key}.")
        try:
            factor = float(raw_factor)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid conversion factor for HS {hs_code}: {raw_factor!r}") from exc
        if not math.isfinite(factor) or factor < 0:
            raise ValueError(f"Conversion factor for HS {hs_code} must be finite and non-negative.")
        pattern = f"*_{hs_code}_M_{settings.year}_partners.csv"
        paths = sorted(year_root.rglob(pattern))
        if not paths:
            raise FileNotFoundError(
                f"No import-by-partner files found for year={settings.year}, HS={hs_code}: "
                f"{year_root / pattern}"
            )
        by_name: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            by_name[path.name].append(path)
        duplicates = {name: values for name, values in by_name.items() if len(values) > 1}
        if duplicates:
            example_name, example_paths = next(iter(duplicates.items()))
            raise ValueError(
                f"Duplicate raw trade files would double-count importer data for HS {hs_code}: "
                f"{example_name} -> {', '.join(str(path) for path in example_paths)}"
            )
        for path in paths:
            try:
                importer_id = int(path.name.split("_", 1)[0])
            except ValueError:
                continue
            if importer_id == 0:
                continue
            frame = pd.read_csv(
                path,
                usecols=lambda column: column in {"partnerCode", "qtyUnitAbbr", "qty", "netWgt"},
            )
            if "partnerCode" not in frame.columns:
                continue
            partners = pd.to_numeric(frame["partnerCode"], errors="coerce")
            tonnes = _quantity_to_tonnes(frame)
            for exporter, quantity in zip(partners.tolist(), tonnes.tolist()):
                if pd.isna(exporter):
                    continue
                exporter_id = int(exporter)
                quantity_value = float(quantity)
                # partnerCode=0 is the World aggregate and must not be mixed with bilateral rows.
                if exporter_id == 0 or quantity_value <= EPSILON:
                    continue
                key = (hs_code, exporter_id, importer_id)
                aggregated[key]["quantity"] += quantity_value
                aggregated[key]["files"].append(str(path))
        for (loaded_hs, exporter_id, importer_id), values in list(aggregated.items()):
            if loaded_hs != hs_code:
                continue
            values["factor"] = factor

    return [
        TradeRecord(
            transition=transition_key,
            hs_code=hs_code,
            importer_id=importer_id,
            exporter_id=exporter_id,
            raw_quantity_tonnes=float(values["quantity"]),
            manual_conversion_factor=float(values["factor"]),
            configured_conversion_factor=float(values["factor"]),
            target_product=settings.post_trade_products.get(transition_key, {}).get(hs_code, ""),
            source_files=sorted(set(values["files"])),
        )
        for (hs_code, exporter_id, importer_id), values in sorted(aggregated.items())
    ]
