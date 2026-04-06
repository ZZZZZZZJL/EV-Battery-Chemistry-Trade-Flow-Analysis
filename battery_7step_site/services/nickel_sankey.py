from __future__ import annotations

from typing import Any

from battery_7step_site.services.datasets import dataset_status, load_dataset_config
from battery_7step_site.services.nickel_data import EPSILON, YEARS, NickelYearInputs, TradeFlow, load_year_inputs
from battery_7step_site.services.reference import load_reference_maps
from battery_7step_site.services.shared_sankey import (
    DEFAULT_THEME,
    DEFAULT_REFERENCE_QTY,
    SPECIAL_NODE_POSITIONS,
    SORT_MODES,
    SPECIAL_COLORS,
    STAGE_LABELS,
    STAGE_ORDER,
    THEME_MODES,
    VIEW_MODES,
    SankeyBuilder,
    _clip,
    _resolve_balance_adjustment as _shared_resolve_balance_adjustment,
    add_country_trade_section,
    add_shared_pool_chem_trade_section,
    add_stage_sink_links,
    make_payload,
)


def _resolve_balance_adjustment(
    balance_value: float,
    known_external_incoming: float,
    known_exports: float,
) -> tuple[float, float]:
    return _shared_resolve_balance_adjustment(
        balance_value,
        known_external_incoming,
        known_exports,
        EPSILON,
    )


def _make_builder(inputs: NickelYearInputs) -> SankeyBuilder:
    config = load_dataset_config()
    id_to_name, id_to_iso3, color_map, region_map = load_reference_maps(config["referenceFile"], inputs.country_ids)
    return SankeyBuilder(id_to_name, id_to_iso3, color_map, region_map)


def _processing_direct_local(inputs: NickelYearInputs) -> dict[int, float]:
    return {
        country_id: inputs.mining_battery.get(country_id, 0.0) + inputs.mining_unrelated.get(country_id, 0.0)
        for country_id in set(inputs.mining_total) | set(inputs.processing_total)
    }


def _build_country_payload(inputs: NickelYearInputs):
    builder = _make_builder(inputs)
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S1",
        post_stage="S2",
        target_stage="S3",
        source_totals=inputs.mining_total,
        trade_supply=inputs.mining_concentrate,
        direct_local=_processing_direct_local(inputs),
        balance_map=inputs.processing_balance,
        target_totals=inputs.processing_total,
        known_trade=inputs.trade1,
        labels={
            "non_source": "From Non-Mining Countries",
            "unknown_source": "Unknown Mining Source",
            "non_target": "Mining to Non-Processing Countries",
            "unknown_target": "Mining to Unknown Destination",
            "non_source_slug": "non_mining_source",
            "unknown_source_slug": "unknown_mining_source",
            "non_target_slug": "non_processing_sink",
            "unknown_target_slug": "unknown_processing_sink",
        },
    )
    add_stage_sink_links(
        builder,
        epsilon=EPSILON,
        source_stage="S3",
        sink_stage="S4",
        values=inputs.processing_unrelated,
        slug="processing_unrelated",
        label="Processing Unrelated",
        color=SPECIAL_COLORS["processing_unrelated"],
    )
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S3",
        post_stage="S4",
        target_stage="S5",
        source_totals=inputs.processing_total,
        trade_supply=inputs.processing_battery,
        direct_local={},
        balance_map=inputs.refining_balance,
        target_totals=inputs.refining_total,
        known_trade=inputs.trade2,
        labels={
            "non_source": "From Non-Processing Countries",
            "unknown_source": "Unknown Processing Source",
            "non_target": "Processing to Non-Refining Countries",
            "unknown_target": "Processing to Unknown Destination",
            "non_source_slug": "non_processing_source",
            "unknown_source_slug": "unknown_processing_source",
            "non_target_slug": "non_refining_sink",
            "unknown_target_slug": "unknown_refining_sink",
        },
    )
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S5",
        post_stage="S6",
        target_stage="S7",
        source_totals=inputs.refining_total,
        trade_supply=inputs.refining_total,
        direct_local={},
        balance_map=inputs.cathode_balance,
        target_totals=inputs.cathode_total,
        known_trade=inputs.trade3,
        labels={
            "non_source": "From Non-Refining Countries",
            "unknown_source": "Unknown Refining Source",
            "non_target": "Refining to Non-Cathode Countries",
            "unknown_target": "Refining to Unknown Destination",
            "non_source_slug": "non_refining_source",
            "unknown_source_slug": "unknown_refining_source",
            "non_target_slug": "non_cathode_sink",
            "unknown_target_slug": "unknown_cathode_sink",
        },
    )
    return builder.nodes, builder.links


def _build_chemistry_payload(inputs: NickelYearInputs, aggregate_display: bool):
    builder = _make_builder(inputs)
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S1",
        post_stage="S2",
        target_stage="S3",
        source_totals=inputs.mining_total,
        trade_supply=inputs.mining_concentrate,
        direct_local=_processing_direct_local(inputs),
        balance_map=inputs.processing_balance,
        target_totals=inputs.processing_total,
        known_trade=inputs.trade1,
        labels={
            "non_source": "From Non-Mining Countries",
            "unknown_source": "Unknown Mining Source",
            "non_target": "Mining to Non-Processing Countries",
            "unknown_target": "Mining to Unknown Destination",
            "non_source_slug": "non_mining_source",
            "unknown_source_slug": "unknown_mining_source",
            "non_target_slug": "non_processing_sink",
            "unknown_target_slug": "unknown_processing_sink",
        },
    )
    add_stage_sink_links(
        builder,
        epsilon=EPSILON,
        source_stage="S3",
        sink_stage="S4",
        values=inputs.processing_unrelated,
        slug="processing_unrelated",
        label="Processing Unrelated",
        color=SPECIAL_COLORS["processing_unrelated"],
    )
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S3",
        post_stage="S4",
        target_stage="S5",
        source_totals=inputs.processing_total,
        trade_supply=inputs.processing_battery,
        direct_local={},
        balance_map=inputs.refining_balance,
        target_totals=inputs.refining_total,
        known_trade=inputs.trade2,
        labels={
            "non_source": "From Non-Processing Countries",
            "unknown_source": "Unknown Processing Source",
            "non_target": "Processing to Non-Refining Countries",
            "unknown_target": "Processing to Unknown Destination",
            "non_source_slug": "non_processing_source",
            "unknown_source_slug": "unknown_processing_source",
            "non_target_slug": "non_refining_sink",
            "unknown_target_slug": "unknown_refining_sink",
        },
    )
    add_shared_pool_chem_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S5",
        post_stage="S6",
        target_stage="S7",
        source_totals=inputs.refining_total,
        trade_supply=inputs.refining_total,
        target_totals_by_category={
            "NCM": inputs.cathode_ncm,
            "NCA": inputs.cathode_nca,
        },
        balance_by_category={
            "NCM": inputs.cathode_ncm_balance,
            "NCA": inputs.cathode_nca_balance,
        },
        known_trade=inputs.trade3,
        source_role="Refining",
        target_role="Cathode",
        aggregate_display=aggregate_display,
    )
    return builder.nodes, builder.links


def build_app_payload(
    year: int,
    view_mode: str,
    reference_qty: float = DEFAULT_REFERENCE_QTY,
    sort_modes: dict[str, str] | None = None,
    stage_orders: dict[str, list[str]] | None = None,
    special_positions: dict[str, str] | None = None,
    aggregate_counts: dict[str, int] | None = None,
    theme: str = DEFAULT_THEME,
) -> dict[str, Any]:
    if year not in YEARS:
        raise ValueError(f"Unsupported year: {year}")
    if theme not in THEME_MODES:
        raise ValueError(f"Unsupported theme: {theme}")

    inputs = load_year_inputs(year)
    if view_mode == "country":
        nodes, links = _build_country_payload(inputs)
    elif view_mode == "chemistry":
        nodes, links = _build_chemistry_payload(inputs, aggregate_display=False)
    elif view_mode == "chemistry_only":
        nodes, links = _build_chemistry_payload(inputs, aggregate_display=True)
    else:
        raise ValueError(f"Unsupported view mode: {view_mode}")

    config = load_dataset_config()
    notes = [
        "Year range is fixed to 2020-2024 because cathode and trade files only cover those five years.",
        "Refining totals use the blank Feedstock row in Nickel_Refining_Final.xlsx as the stage total.",
        "Trade data are read from the import folders only, matching the prompt requirement.",
        f"Reference quantity is set to {reference_qty:,.0f} t. Lower values enlarge nodes, and the figure height expands from the tallest full stage stack so all nodes keep the planned gap.",
        "The fixed reference node beneath S7 keeps the same visual size in every export; changing Reference Quantity only changes how many tons that box represents.",
        "Continent sorting follows the region column in ListOfreference.xlsx.",
    ]
    if view_mode == "chemistry_only":
        notes.append("Chemistry-only view aggregates S6 and S7 nodes globally by chemistry while keeping the country-level balancing logic.")
    if 540 in inputs.country_ids:
        notes.append("New Caledonia has no reference color in ListOfreference.xlsx, so the site assigns a unique fallback color.")
    return make_payload(
        nodes=nodes,
        links=links,
        year=year,
        metal="Ni",
        view_mode=view_mode,
        reference_qty=reference_qty,
        sort_modes=sort_modes,
        stage_orders=stage_orders,
        notes=notes,
        dataset_status=dataset_status(config),
        epsilon=EPSILON,
        special_positions=special_positions,
        aggregate_counts=aggregate_counts,
        theme=theme,
    )


__all__ = [
    "DEFAULT_REFERENCE_QTY",
    "DEFAULT_THEME",
    "SPECIAL_NODE_POSITIONS",
    "SORT_MODES",
    "STAGE_LABELS",
    "STAGE_ORDER",
    "THEME_MODES",
    "VIEW_MODES",
    "_resolve_balance_adjustment",
    "build_app_payload",
]
