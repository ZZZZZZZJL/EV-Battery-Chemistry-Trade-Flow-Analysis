from __future__ import annotations

from colorsys import hls_to_rgb
from functools import lru_cache

import pandas as pd


def normalize_reference_color(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    color = str(value).strip().lstrip("#").upper()
    if len(color) == 3:
        color = "".join(channel * 2 for channel in color)
    if len(color) != 6 or any(channel not in "0123456789ABCDEF" for channel in color):
        return None
    return f"#{color}"


@lru_cache(maxsize=4)
def load_reference_frame(reference_file: str) -> pd.DataFrame:
    frame = pd.read_excel(reference_file).copy()
    frame = frame.rename(columns={"text": "name", "reporterCodeIsoAlpha3": "iso3"})
    if "name" not in frame.columns:
        frame["name"] = frame.get("reporterDesc", "")
    if "iso3" not in frame.columns:
        frame["iso3"] = ""
    if "color" not in frame.columns:
        frame["color"] = None
    if "region" not in frame.columns:
        frame["region"] = "Unknown"
    frame["region"] = frame["region"].fillna("Unknown").astype(str).str.strip()
    frame.loc[frame["region"].eq(""), "region"] = "Unknown"
    frame["color"] = frame["color"].apply(normalize_reference_color)
    return frame


def _hsl_to_hex(hue: float, saturation: float, lightness: float) -> str:
    red, green, blue = hls_to_rgb(hue, lightness, saturation)
    return "#%02x%02x%02x" % (int(red * 255), int(green * 255), int(blue * 255))


def _build_fallback_palette(country_ids: list[int], used: set[str]) -> dict[int, str]:
    palette: dict[int, str] = {}
    for index, country_id in enumerate(sorted(country_ids)):
        hue = (index * 0.618033988749895) % 1.0
        saturation = min(0.58 + (index % 3) * 0.08, 0.82)
        lightness = min(0.4 + ((index // 3) % 3) * 0.06, 0.62)
        candidate = _hsl_to_hex(hue, saturation, lightness)
        while candidate.upper() in used:
            hue = (hue + 0.073) % 1.0
            candidate = _hsl_to_hex(hue, saturation, lightness)
        palette[country_id] = candidate
        used.add(candidate.upper())
    return palette


def load_reference_maps(
    reference_file: str,
    country_ids: list[int],
) -> tuple[dict[int, str], dict[int, str], dict[int, str], dict[int, str]]:
    frame = load_reference_frame(reference_file)
    name_map = {
        int(row.id): str(row.name).strip()
        for row in frame[["id", "name"]].itertuples(index=False)
        if pd.notna(row.id)
    }
    iso3_map = {
        int(row.id): str(row.iso3 or "").strip()
        for row in frame[["id", "iso3"]].itertuples(index=False)
        if pd.notna(row.id)
    }
    color_map = {
        int(row.id): row.color
        for row in frame[["id", "color"]].itertuples(index=False)
        if pd.notna(row.id) and isinstance(row.color, str) and row.color
    }
    region_map = {
        int(row.id): str(row.region).strip() or "Unknown"
        for row in frame[["id", "region"]].itertuples(index=False)
        if pd.notna(row.id)
    }
    missing = [country_id for country_id in sorted(set(country_ids)) if country_id not in color_map]
    if missing:
        used_colors = {value.upper() for value in color_map.values()}
        color_map.update(_build_fallback_palette(missing, used_colors))
    return name_map, iso3_map, color_map, region_map
