from __future__ import annotations

import glob
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from battery_7step_site.services.datasets import load_dataset_config


YEARS = [2020, 2021, 2022, 2023, 2024]
FIRST_TRADE_FOLDER = "1st_post_trade/Ni_260400"
SECOND_TRADE_FOLDERS = ("2nd_post_trade/Ni_750110", "2nd_post_trade/Ni_750120", "2nd_post_trade/Ni_750300", "2nd_post_trade/Ni_750400")
THIRD_TRADE_FOLDER = "3rd_post_trade/Ni_283324"
EPSILON = 1e-9


@dataclass(frozen=True)
class TradeFlow:
    exporter: int
    importer: int
    value: float


@dataclass(frozen=True)
class NickelYearInputs:
    mining_total: dict[int, float]
    mining_battery: dict[int, float]
    mining_unrelated: dict[int, float]
    mining_concentrate: dict[int, float]
    processing_total: dict[int, float]
    processing_battery: dict[int, float]
    processing_unrelated: dict[int, float]
    processing_balance: dict[int, float]
    refining_total: dict[int, float]
    refining_balance: dict[int, float]
    cathode_total: dict[int, float]
    cathode_ncm: dict[int, float]
    cathode_nca: dict[int, float]
    cathode_balance: dict[int, float]
    cathode_ncm_balance: dict[int, float]
    cathode_nca_balance: dict[int, float]
    trade1: tuple[TradeFlow, ...]
    trade2: tuple[TradeFlow, ...]
    trade3: tuple[TradeFlow, ...]

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
        ):
            ids.update(mapping.keys())
        for flow in (*self.trade1, *self.trade2, *self.trade3):
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


@lru_cache(maxsize=8)
def _load_production_table(name: str) -> pd.DataFrame:
    config = load_dataset_config()
    frame = pd.read_excel(Path(config["productionRoot"]) / name)
    return _coerce_year_columns(frame)


def _mining_maps(year: int) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    frame = _load_production_table("Nickel_Mining_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    battery = _year_map(frame, year, frame["Product"].astype(str).eq("Battery-related"))
    unrelated = _year_map(frame, year, frame["Product"].astype(str).eq("Unrelated"))
    concentrate = _year_map(frame, year, frame["Product"].astype(str).eq("Nickel concentrate"))
    return total, battery, unrelated, concentrate


def _processing_maps(year: int) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    frame = _load_production_table("Nickel_Processing_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    battery = _year_map(frame, year, frame["Product"].astype(str).eq("Battery-related"))
    unrelated = _year_map(frame, year, frame["Product"].astype(str).eq("Unrelated"))
    balance_mask = frame["Product"].astype(str).eq("Balance") & _blank_mask(frame["Feedstock"])
    balance = _year_map(frame, year, balance_mask)
    return total, battery, unrelated, balance


def _refining_maps(year: int) -> tuple[dict[int, float], dict[int, float]]:
    frame = _load_production_table("Nickel_Refining_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Feedstock"]))
    balance = _year_map(frame, year, frame["Feedstock"].astype(str).eq("Balance"))
    return total, balance


def _cathode_maps(
    year: int,
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    frame = _load_production_table("Nickel_Cathode_Final.xlsx")
    total = _year_map(frame, year, _blank_mask(frame["Product"]))
    ncm = _year_map(frame, year, frame["Product"].astype(str).eq("NCM"))
    nca = _year_map(frame, year, frame["Product"].astype(str).eq("NCA"))
    balance = _year_map(frame, year, frame["Product"].astype(str).eq("Balance"))
    ncm_balance = _year_map(frame, year, frame["Product"].astype(str).eq("NCM Balance"))
    nca_balance = _year_map(frame, year, frame["Product"].astype(str).eq("NCA Balance"))
    return total, ncm, nca, balance, ncm_balance, nca_balance


@lru_cache(maxsize=24)
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


def _merge_trade_flows(*trade_groups: tuple[TradeFlow, ...]) -> tuple[TradeFlow, ...]:
    merged: dict[tuple[int, int], float] = {}
    for group in trade_groups:
        for flow in group:
            key = (int(flow.exporter), int(flow.importer))
            merged[key] = merged.get(key, 0.0) + float(flow.value)
    return tuple(
        TradeFlow(exporter=exporter, importer=importer, value=value)
        for (exporter, importer), value in sorted(merged.items())
        if abs(value) > EPSILON
    )


@lru_cache(maxsize=16)
def load_year_inputs(year: int) -> NickelYearInputs:
    if year not in YEARS:
        raise ValueError(f"Unsupported year: {year}")
    mining_total, mining_battery, mining_unrelated, mining_concentrate = _mining_maps(year)
    processing_total, processing_battery, processing_unrelated, processing_balance = _processing_maps(year)
    refining_total, refining_balance = _refining_maps(year)
    cathode_total, cathode_ncm, cathode_nca, cathode_balance, cathode_ncm_balance, cathode_nca_balance = _cathode_maps(year)
    return NickelYearInputs(
        mining_total=mining_total,
        mining_battery=mining_battery,
        mining_unrelated=mining_unrelated,
        mining_concentrate=mining_concentrate,
        processing_total=processing_total,
        processing_battery=processing_battery,
        processing_unrelated=processing_unrelated,
        processing_balance=processing_balance,
        refining_total=refining_total,
        refining_balance=refining_balance,
        cathode_total=cathode_total,
        cathode_ncm=cathode_ncm,
        cathode_nca=cathode_nca,
        cathode_balance=cathode_balance,
        cathode_ncm_balance=cathode_ncm_balance,
        cathode_nca_balance=cathode_nca_balance,
        trade1=_load_trade_flows(FIRST_TRADE_FOLDER, year),
        trade2=_merge_trade_flows(*(_load_trade_flows(folder, year) for folder in SECOND_TRADE_FOLDERS)),
        trade3=_load_trade_flows(THIRD_TRADE_FOLDER, year),
    )
