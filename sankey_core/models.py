from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EPSILON = 1e-9


@dataclass(frozen=True)
class ProductionStage:
    key: str
    label: str


@dataclass(frozen=True)
class TransitionSpec:
    key: str
    label: str
    source_stage: str
    target_stage: str


@dataclass(frozen=True)
class RouteSpec:
    key: str
    production_stages: tuple[ProductionStage, ...]
    transitions: tuple[TransitionSpec, ...]


@dataclass(frozen=True)
class DisplayStage:
    key: str
    label: str
    production_key: str | None = None
    transition_key: str | None = None


@dataclass(frozen=True)
class ReferenceMaps:
    names: dict[int, str]
    iso3: dict[int, str]
    colors: dict[int, str]
    regions: dict[int, str]


@dataclass(frozen=True)
class ProductionData:
    totals: dict[str, dict[int, float]]
    labels: dict[int, str]
    cathode_chemistry: dict[str, dict[int, float]]
    stage_chemistry: dict[str, dict[str, dict[int, float]]] = field(default_factory=dict)
    ignored_rows: tuple[dict[str, Any], ...] = ()
    sheet_summary_rows: tuple[dict[str, Any], ...] = ()


@dataclass
class TradeRecord:
    transition: str
    hs_code: str
    importer_id: int
    exporter_id: int
    raw_quantity_tonnes: float
    manual_conversion_factor: float
    configured_conversion_factor: float = 0.0
    target_product: str = ""
    chemistry_factor_basis: str = ""
    chemistry_factor_detail: str = ""
    source_files: list[str] = field(default_factory=list)
    classification: str = ""
    converted_quantity_before_scaling: float = 0.0
    available_source_production: float = 0.0
    exporter_total_before_scaling: float = 0.0
    production_scaling_multiplier: float = 1.0
    effective_conversion_factor: float = 0.0
    final_trade_quantity_tonnes: float = 0.0
    included_in_sankey: bool = True
    adjustment_reason: str = ""


@dataclass(frozen=True)
class NodeSpec:
    key: str
    stage: str
    label: str
    color: str
    kind: str
    hover: str
    region: str


@dataclass(frozen=True)
class LinkSpec:
    source: str
    target: str
    value: float
    color: str


@dataclass(frozen=True)
class BuildResult:
    nodes: dict[str, NodeSpec]
    links: tuple[LinkSpec, ...]
    conversion_rows: tuple[dict[str, Any], ...]
    balance_rows: tuple[dict[str, Any], ...]
    stage_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Settings:
    metal: str
    year: int
    route: str
    merge_processing_refining: bool
    show_pcam: bool
    show_battery: bool
    cathode_view: str
    chemistry_stage_scope: str
    merge_lmfp_into_lfp: bool
    shared_hs_trade_owner: str
    chemistry_conversion_factors: dict[str, float]
    use_production_data: bool
    production_source: str
    production_sheets: tuple[str, ...] | None
    production_root: Path
    trade_root: Path
    reference_file: Path
    post_trade_hs: dict[str, dict[str, float]]
    post_trade_products: dict[str, dict[str, str]]
    output_root: Path
    reference_quantity: float
    theme: str
    sort_mode: str
    image_width: int
    image_scale: float
    label_font_size: int
    # Per-stage production selection. The legacy production_source/root fields
    # above remain available so older config files and callers still work.
    production_sources_by_stage: dict[str, str] = field(default_factory=dict)
    production_roots: dict[str, Path] = field(default_factory=dict)
    production_all_status_sources: frozenset[str] = frozenset()
    output_basename: str | None = None
    country_label_mode: str = "full"
    flow_transparency_threshold: float = 0.0
    node_transparency_threshold: float = 0.0
    preserved_country_ids: frozenset[int] = frozenset()
