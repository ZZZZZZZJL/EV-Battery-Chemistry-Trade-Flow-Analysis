from __future__ import annotations

import glob
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from battery_7step_site.services.datasets import load_dataset_config


YEARS = [2020, 2021, 2022, 2023, 2024]
FIRST_TRADE_FOLDERS = ("1st_post_trade/Co_260500",)
SECOND_TRADE_FOLDERS = (
    "2nd_post_trade/Co_282200",
    "2nd_post_trade/Co_810520",
    "2nd_post_trade/Co_810530",
)
THIRD_TRADE_FOLDERS = ("3rd_post_trade/Co_283329",)
COBALT_MODES = ("mid", "max", "min")
COBALT_MODE_LABELS = {
    "mid": "Middle",
    "max": "Max",
    "min": "Min",
}
DEFAULT_COBALT_MODE = "mid"
EPSILON = 1e-9


@dataclass(frozen=True)
class TradeFlow:
    exporter: int
    importer: int
    value: float


@dataclass(frozen=True)
class CobaltYearInputs:
    mining_total: dict[int, float]
    mining_battery: dict[int, float]
    mining_concentrate: dict[int, float]
    mining_sulphate: dict[int, float]
    processing_total: dict[int, float]
    processing_unrelated: dict[int, float]
    refining_max: dict[int, float]
    refining_mid: dict[int, float]
    refining_min: dict[int, float]
    refining_max_balance: dict[int, float]
    refining_mid_balance: dict[int, float]
    refining_min_balance: dict[int, float]
    cathode_total: dict[int, float]
    cathode_ncm: dict[int, float]
    cathode_nca: dict[int, float]
    cathode_max_total_balance: dict[int, float]
    cathode_mid_total_balance: dict[int, float]
    cathode_min_total_balance: dict[int, float]
    cathode_max_ncm_balance: dict[int, float]
    cathode_mid_ncm_balance: dict[int, float]
    cathode_min_ncm_balance: dict[int, float]
    cathode_max_nca_balance: dict[int, float]
    cathode_mid_nca_balance: dict[int, float]
    cathode_min_nca_balance: dict[int, float]
    trade1: tuple[TradeFlow, ...]
    trade2: tuple[TradeFlow, ...]
    trade3: tuple[TradeFlow, ...]

    @property
    def country_ids(self) -> list[int]:
        ids = set()
        for mapping in (
            self.mining_total,
            self.processing_total,
            self.refining_max,
            self.refining_mid,
            self.refining_min,
            self.cathode_total,
            self.cathode_ncm,
            self.cathode_nca,
        ):
            ids.update(mapping.keys())
        for flow in (*self.trade1, *self.trade2, *self.trade3):
            ids.add(flow.exporter)
            ids.add(flow.importer)
        return sorted(ids)


def resolve_cobalt_mode(mode: str) -> str:
    normalized = str(mode).strip().lower()
    if normalized not in COBALT_MODES:
        raise ValueError(f"Unsupported cobalt mode: {mode}")
    return normalized


def _coerce_year_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for year in YEARS:
        if year in result.columns:
            result[year] = pd.to_numeric(result[year], errors="coerce").fillna(0.0)
    return result


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


def _product_mask(series: pd.Series, *choices: str) -> pd.Series:
    normalized = series.fillna("").astype(str).str.strip()
    return normalized.isin(choices)


def _year_map(frame: pd.DataFrame, year: int, mask: pd.Series) -> dict[int, float]:
    subset = frame.loc[mask, ["id", year]].copy()
    subset["id"] = pd.to_numeric(subset["id"], errors="coerce")
    subset[year] = pd.to_numeric(subset[year], errors="coerce").fillna(0.0)
    grouped = subset.dropna(subset=["id"]).groupby("id", as_index=False)[year].sum()
    return {
        int(row.id): float(row[year])
        for _, row in grouped.iterrows()
        if abs(float(row[year])) > EPSILON
    }


def _difference_map(left: dict[int, float], right: dict[int, float]) -> dict[int, float]:
    keys = set(left) | set(right)
    return {
        int(key): float(left.get(key, 0.0)) - float(right.get(key, 0.0))
        for key in keys
        if abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) > EPSILON
    }


def _sum_maps(*mappings: dict[int, float]) -> dict[int, float]:
    result: dict[int, float] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            result[int(key)] = result.get(int(key), 0.0) + float(value)
    return {
        key: value
        for key, value in result.items()
        if abs(value) > EPSILON
    }


def _share_map(total: dict[int, float], part: dict[int, float]) -> dict[int, float]:
    shares: dict[int, float] = {}
    for key in set(total) | set(part):
        denominator = float(total.get(key, 0.0))
        if denominator <= EPSILON:
            continue
        numerator = float(part.get(key, 0.0))
        if abs(numerator) <= EPSILON:
            continue
        shares[int(key)] = numerator / denominator
    return shares


def _allocated_balance_map(
    cathode_map: dict[int, float],
    refining_total: dict[int, float],
    share_map: dict[int, float],
) -> dict[int, float]:
    keys = set(cathode_map) | set(refining_total) | set(share_map)
    result: dict[int, float] = {}
    for key in keys:
        value = float(cathode_map.get(key, 0.0)) - float(refining_total.get(key, 0.0)) * float(share_map.get(key, 0.0))
        if abs(value) > EPSILON:
            result[int(key)] = value
    return result


@lru_cache(maxsize=12)
def _load_production_table(name: str) -> pd.DataFrame:
    config = load_dataset_config()
    frame = pd.read_excel(Path(config["productionRoot"]) / name)
    return _coerce_year_columns(frame)


def _mining_maps(year: int) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    frame = _load_production_table("Cobalt_Mining_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    battery = _year_map(frame, year, _product_mask(frame["Product"], "Battery related"))
    concentrate = _year_map(frame, year, _product_mask(frame["Product"], "Cobalt concentrate"))
    sulphate = _year_map(frame, year, _product_mask(frame["Product"], "Cobalt sulphate"))
    return total, battery, concentrate, sulphate


def _processing_maps(year: int) -> tuple[dict[int, float], dict[int, float]]:
    frame = _load_production_table("Cobalt_Processing_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    unrelated = _year_map(frame, year, _product_mask(frame["Product"], "Unrelated"))
    return total, unrelated


def _refining_maps(
    year: int,
) -> tuple[
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
]:
    frame = _load_production_table("Cobalt_Refining_Final.xlsx")
    max_total = _year_map(frame, year, _product_mask(frame["Product"], "Max battery related"))
    mid_total = _year_map(frame, year, _product_mask(frame["Product"], "Middle battery related", "Mid battery related"))
    min_total = _year_map(frame, year, _product_mask(frame["Product"], "Min battery related"))
    max_balance = _year_map(frame, year, _product_mask(frame["Product"], "Max balance"))
    mid_balance = _year_map(frame, year, _product_mask(frame["Product"], "Middle balance", "Mid balance"))
    min_balance = _year_map(frame, year, _product_mask(frame["Product"], "Min balance"))
    return max_total, mid_total, min_total, max_balance, mid_balance, min_balance


def _cathode_maps(
    year: int,
) -> tuple[
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
]:
    frame = _load_production_table("Cobalt_Cathode_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    ncm = _year_map(frame, year, _product_mask(frame["Product"], "NCM"))
    nca = _year_map(frame, year, _product_mask(frame["Product"], "NCA"))
    max_total_balance = _year_map(frame, year, _product_mask(frame["Product"], "Max NCM+NCA Balance"))
    mid_total_balance = _year_map(frame, year, _product_mask(frame["Product"], "Middle NCM+NCA Balance", "Mid NCM+NCA Balance"))
    min_total_balance = _year_map(frame, year, _product_mask(frame["Product"], "Min NCM+NCA Balance"))
    max_ncm_balance = _year_map(frame, year, _product_mask(frame["Product"], "Max NCM Balance"))
    mid_ncm_balance = _year_map(frame, year, _product_mask(frame["Product"], "Middle NCM Balance", "Mid NCM Balance"))
    min_ncm_balance = _year_map(frame, year, _product_mask(frame["Product"], "Min NCM Balance"))
    max_nca_balance = _year_map(frame, year, _product_mask(frame["Product"], "Max NCA Balance"))
    mid_nca_balance = _year_map(frame, year, _product_mask(frame["Product"], "Middle NCA Balance", "Mid NCA Balance"))
    min_nca_balance = _year_map(frame, year, _product_mask(frame["Product"], "Min NCA Balance"))
    return (
        total,
        ncm,
        nca,
        max_total_balance,
        mid_total_balance,
        min_total_balance,
        max_ncm_balance,
        mid_ncm_balance,
        min_ncm_balance,
        max_nca_balance,
        mid_nca_balance,
        min_nca_balance,
    )


@lru_cache(maxsize=64)
def _load_trade_flows(folder_name: str, year: int) -> tuple[TradeFlow, ...]:
    config = load_dataset_config()
    folder = Path(config["tradeRoot"]) / folder_name
    flows: list[TradeFlow] = []
    if not folder.exists():
        return tuple()
    for file_name in glob.glob(str(folder / "*_combined.csv")):
        try:
            importer = int(Path(file_name).name.split("_")[0])
        except ValueError:
            continue
        if importer == 0:
            continue
        frame = pd.read_csv(file_name, usecols=["Year", "Partner ID", "Quantity"], engine="c")
        filtered = frame[frame["Year"] == year]
        for _, row in filtered.iterrows():
            try:
                exporter = int(row["Partner ID"])
                value = float(row["Quantity"])
            except (TypeError, ValueError):
                continue
            if exporter == 0 or value <= EPSILON:
                continue
            flows.append(TradeFlow(exporter=exporter, importer=importer, value=value))
    return tuple(flows)


@lru_cache(maxsize=32)
def _load_trade_flow_group(folder_names: tuple[str, ...], year: int) -> tuple[TradeFlow, ...]:
    flows: list[TradeFlow] = []
    for folder_name in folder_names:
        flows.extend(_load_trade_flows(folder_name, year))
    return tuple(flows)


@lru_cache(maxsize=16)
def load_year_inputs(year: int) -> CobaltYearInputs:
    if year not in YEARS:
        raise ValueError(f"Unsupported year: {year}")

    mining_total, mining_battery, mining_concentrate, mining_sulphate = _mining_maps(year)
    processing_total, processing_unrelated = _processing_maps(year)
    (
        refining_max,
        refining_mid,
        refining_min,
        refining_max_balance,
        refining_mid_balance_raw,
        refining_min_balance,
    ) = _refining_maps(year)
    (
        cathode_total,
        cathode_ncm,
        cathode_nca,
        cathode_max_total_balance,
        cathode_mid_total_balance_raw,
        cathode_min_total_balance,
        cathode_max_ncm_balance,
        cathode_mid_ncm_balance_raw,
        cathode_min_ncm_balance,
        cathode_max_nca_balance,
        cathode_mid_nca_balance_raw,
        cathode_min_nca_balance,
    ) = _cathode_maps(year)

    if not refining_mid_balance_raw:
        refining_mid_balance = _sum_maps(
            _difference_map(refining_mid, processing_total),
            processing_unrelated,
        )
    else:
        refining_mid_balance = refining_mid_balance_raw

    ncm_share = _share_map(cathode_total, cathode_ncm)
    nca_share = _share_map(cathode_total, cathode_nca)

    cathode_mid_total_balance = (
        cathode_mid_total_balance_raw
        if cathode_mid_total_balance_raw
        else _difference_map(cathode_total, refining_mid)
    )
    cathode_mid_ncm_balance = (
        cathode_mid_ncm_balance_raw
        if cathode_mid_ncm_balance_raw
        else _allocated_balance_map(cathode_ncm, refining_mid, ncm_share)
    )
    cathode_mid_nca_balance = (
        cathode_mid_nca_balance_raw
        if cathode_mid_nca_balance_raw
        else _allocated_balance_map(cathode_nca, refining_mid, nca_share)
    )

    return CobaltYearInputs(
        mining_total=mining_total,
        mining_battery=mining_battery,
        mining_concentrate=mining_concentrate,
        mining_sulphate=mining_sulphate,
        processing_total=processing_total,
        processing_unrelated=processing_unrelated,
        refining_max=refining_max,
        refining_mid=refining_mid,
        refining_min=refining_min,
        refining_max_balance=refining_max_balance,
        refining_mid_balance=refining_mid_balance,
        refining_min_balance=refining_min_balance,
        cathode_total=cathode_total,
        cathode_ncm=cathode_ncm,
        cathode_nca=cathode_nca,
        cathode_max_total_balance=cathode_max_total_balance,
        cathode_mid_total_balance=cathode_mid_total_balance,
        cathode_min_total_balance=cathode_min_total_balance,
        cathode_max_ncm_balance=cathode_max_ncm_balance,
        cathode_mid_ncm_balance=cathode_mid_ncm_balance,
        cathode_min_ncm_balance=cathode_min_ncm_balance,
        cathode_max_nca_balance=cathode_max_nca_balance,
        cathode_mid_nca_balance=cathode_mid_nca_balance,
        cathode_min_nca_balance=cathode_min_nca_balance,
        trade1=_load_trade_flow_group(FIRST_TRADE_FOLDERS, year),
        trade2=_load_trade_flow_group(SECOND_TRADE_FOLDERS, year),
        trade3=_load_trade_flow_group(THIRD_TRADE_FOLDERS, year),
    )


__all__ = [
    "COBALT_MODES",
    "COBALT_MODE_LABELS",
    "DEFAULT_COBALT_MODE",
    "EPSILON",
    "TradeFlow",
    "YEARS",
    "CobaltYearInputs",
    "load_year_inputs",
    "resolve_cobalt_mode",
]
