from __future__ import annotations

import glob
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from battery_7step_site.services.datasets import load_dataset_config


YEARS = [2020, 2021, 2022, 2023, 2024]
FIRST_TRADE_FOLDER = "1st_post_trade/Li_253090"
SECOND_TRADE_FOLDER = "2nd_post_trade/Li_000000"
THIRD_TRADE_HYDROXIDE_FOLDER = "3rd_post_trade/Li_282520"
THIRD_TRADE_CARBONATE_FOLDER = "3rd_post_trade/Li_283691"
EPSILON = 1e-9


@dataclass(frozen=True)
class TradeFlow:
    exporter: int
    importer: int
    value: float


@dataclass(frozen=True)
class LithiumYearInputs:
    mining_total: dict[int, float]
    mining_brine: dict[int, float]
    mining_lithium_ores: dict[int, float]
    processing_total: dict[int, float]
    processing_battery: dict[int, float]
    processing_unrelated: dict[int, float]
    processing_brine_total: dict[int, float]
    processing_lithium_ores_total: dict[int, float]
    processing_brine_balance: dict[int, float]
    processing_lithium_ores_balance: dict[int, float]
    refining_total: dict[int, float]
    refining_hydroxide: dict[int, float]
    refining_carbonate: dict[int, float]
    refining_hydroxide_balance: dict[int, float]
    refining_carbonate_balance: dict[int, float]
    cathode_total: dict[int, float]
    cathode_ncm: dict[int, float]
    cathode_nca: dict[int, float]
    cathode_lfp: dict[int, float]
    cathode_ncm_nca_balance: dict[int, float]
    cathode_ncm_balance: dict[int, float]
    cathode_nca_balance: dict[int, float]
    cathode_lfp_balance: dict[int, float]
    trade1: tuple[TradeFlow, ...]
    trade2: tuple[TradeFlow, ...]
    trade3_hydroxide: tuple[TradeFlow, ...]
    trade3_carbonate: tuple[TradeFlow, ...]

    @property
    def country_ids(self) -> list[int]:
        ids = set()
        for mapping in (
            self.mining_total,
            self.processing_total,
            self.refining_total,
            self.cathode_total,
            self.cathode_ncm,
            self.cathode_nca,
            self.cathode_lfp,
        ):
            ids.update(mapping.keys())
        for flow in (*self.trade1, *self.trade2, *self.trade3_hydroxide, *self.trade3_carbonate):
            ids.add(flow.exporter)
            ids.add(flow.importer)
        return sorted(ids)


def _coerce_year_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for year in YEARS:
        if year in result.columns:
            result[year] = pd.to_numeric(result[year], errors="coerce").fillna(0.0)
    return result


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


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


@lru_cache(maxsize=12)
def _load_production_table(name: str) -> pd.DataFrame:
    config = load_dataset_config()
    frame = pd.read_excel(Path(config["productionRoot"]) / name)
    return _coerce_year_columns(frame)


def _mining_maps(year: int) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
    frame = _load_production_table("Lithium_Mining_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    brine = _year_map(frame, year, frame["Product"].astype(str).eq("Brine"))
    lithium_ores = _year_map(frame, year, frame["Product"].astype(str).eq("Lithium ores"))
    return total, brine, lithium_ores


def _processing_maps(
    year: int,
) -> tuple[
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
    dict[int, float],
]:
    frame = _load_production_table("Lithium_Processing_Final.xlsx")
    feedstock_blank = _blank_mask(frame["Feedstock"])
    product_blank = _blank_mask(frame["Product"])
    total = _year_map(frame, year, feedstock_blank & product_blank)
    battery = _year_map(frame, year, feedstock_blank & frame["Product"].astype(str).eq("Battery-related"))
    unrelated = _year_map(frame, year, feedstock_blank & frame["Product"].astype(str).eq("Unrelated"))
    brine_total = _year_map(frame, year, frame["Feedstock"].astype(str).eq("Brine") & product_blank)
    lithium_ores_total = _year_map(frame, year, frame["Feedstock"].astype(str).eq("Lithium ores") & product_blank)
    brine_balance = _year_map(frame, year, frame["Feedstock"].astype(str).eq("Brine") & frame["Product"].astype(str).eq("Balance"))
    lithium_ores_balance = _year_map(
        frame,
        year,
        frame["Feedstock"].astype(str).eq("Lithium ores") & frame["Product"].astype(str).eq("Balance"),
    )
    return total, battery, unrelated, brine_total, lithium_ores_total, brine_balance, lithium_ores_balance


def _refining_maps(
    year: int,
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    frame = _load_production_table("Lithium_Refining_Final.xlsx")
    feedstock_blank = _blank_mask(frame["Feedstock"])
    total = _year_map(frame, year, feedstock_blank & _blank_mask(frame["Product"]))
    hydroxide = _year_map(frame, year, feedstock_blank & frame["Product"].astype(str).eq("Lithium Hydroxide"))
    carbonate = _year_map(frame, year, feedstock_blank & frame["Product"].astype(str).eq("Lithium Carbonate"))
    hydroxide_balance = _year_map(
        frame,
        year,
        feedstock_blank & frame["Product"].astype(str).eq("Lithium Hydroxide Balance"),
    )
    carbonate_balance = _year_map(
        frame,
        year,
        feedstock_blank & frame["Product"].astype(str).eq("Lithium Carbonate Balance"),
    )
    return total, hydroxide, carbonate, hydroxide_balance, carbonate_balance


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
]:
    frame = _load_production_table("Lithium_Cathode_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    ncm = _year_map(frame, year, frame["Product"].astype(str).eq("NCM"))
    nca = _year_map(frame, year, frame["Product"].astype(str).eq("NCA"))
    lfp = _year_map(frame, year, frame["Product"].astype(str).eq("LFP"))
    ncm_nca_balance = _year_map(frame, year, frame["Product"].astype(str).eq("NCM+NCA Balance"))
    ncm_balance = _year_map(frame, year, frame["Product"].astype(str).eq("NCM Balance"))
    nca_balance = _year_map(frame, year, frame["Product"].astype(str).eq("NCA Balance"))
    lfp_balance = _year_map(frame, year, frame["Product"].astype(str).eq("LFP Balance"))
    return total, ncm, nca, lfp, ncm_nca_balance, ncm_balance, nca_balance, lfp_balance


@lru_cache(maxsize=32)
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


@lru_cache(maxsize=16)
def load_year_inputs(year: int) -> LithiumYearInputs:
    if year not in YEARS:
        raise ValueError(f"Unsupported year: {year}")
    mining_total, mining_brine, mining_lithium_ores = _mining_maps(year)
    (
        processing_total,
        processing_battery,
        processing_unrelated,
        processing_brine_total,
        processing_lithium_ores_total,
        processing_brine_balance,
        processing_lithium_ores_balance,
    ) = _processing_maps(year)
    (
        refining_total,
        refining_hydroxide,
        refining_carbonate,
        refining_hydroxide_balance,
        refining_carbonate_balance,
    ) = _refining_maps(year)
    (
        cathode_total,
        cathode_ncm,
        cathode_nca,
        cathode_lfp,
        cathode_ncm_nca_balance,
        cathode_ncm_balance,
        cathode_nca_balance,
        cathode_lfp_balance,
    ) = _cathode_maps(year)
    return LithiumYearInputs(
        mining_total=mining_total,
        mining_brine=mining_brine,
        mining_lithium_ores=mining_lithium_ores,
        processing_total=processing_total,
        processing_battery=processing_battery,
        processing_unrelated=processing_unrelated,
        processing_brine_total=processing_brine_total,
        processing_lithium_ores_total=processing_lithium_ores_total,
        processing_brine_balance=processing_brine_balance,
        processing_lithium_ores_balance=processing_lithium_ores_balance,
        refining_total=refining_total,
        refining_hydroxide=refining_hydroxide,
        refining_carbonate=refining_carbonate,
        refining_hydroxide_balance=refining_hydroxide_balance,
        refining_carbonate_balance=refining_carbonate_balance,
        cathode_total=cathode_total,
        cathode_ncm=cathode_ncm,
        cathode_nca=cathode_nca,
        cathode_lfp=cathode_lfp,
        cathode_ncm_nca_balance=cathode_ncm_nca_balance,
        cathode_ncm_balance=cathode_ncm_balance,
        cathode_nca_balance=cathode_nca_balance,
        cathode_lfp_balance=cathode_lfp_balance,
        trade1=_load_trade_flows(FIRST_TRADE_FOLDER, year),
        trade2=_load_trade_flows(SECOND_TRADE_FOLDER, year),
        trade3_hydroxide=_load_trade_flows(THIRD_TRADE_HYDROXIDE_FOLDER, year),
        trade3_carbonate=_load_trade_flows(THIRD_TRADE_CARBONATE_FOLDER, year),
    )
