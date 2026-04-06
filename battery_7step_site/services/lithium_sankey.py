from __future__ import annotations

from typing import Any

from battery_7step_site.services.datasets import dataset_status, load_dataset_config
from battery_7step_site.services.lithium_data import EPSILON, YEARS, LithiumYearInputs, TradeFlow, load_year_inputs
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
    _sum_maps,
    add_country_trade_section,
    add_shared_pool_chem_trade_section,
    add_stage_sink_links,
    make_payload,
)


def _make_builder(inputs: LithiumYearInputs) -> SankeyBuilder:
    config = load_dataset_config()
    id_to_name, id_to_iso3, color_map, region_map = load_reference_maps(config["referenceFile"], inputs.country_ids)
    return SankeyBuilder(id_to_name, id_to_iso3, color_map, region_map)


def _positive_difference(left: dict[int, float], *rights: dict[int, float]) -> dict[int, float]:
    result: dict[int, float] = {}
    keys = set(left)
    for mapping in rights:
        keys.update(mapping)
    for key in keys:
        value = float(left.get(key, 0.0))
        for mapping in rights:
            value -= float(mapping.get(key, 0.0))
        if value > EPSILON:
            result[int(key)] = value
    return result


def _combined_third_trade(inputs: LithiumYearInputs) -> tuple[TradeFlow, ...]:
    return inputs.trade3_hydroxide + inputs.trade3_carbonate


def _build_country_payload(inputs: LithiumYearInputs):
    builder = _make_builder(inputs)
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S1",
        post_stage="S2",
        target_stage="S3",
        source_totals=inputs.mining_total,
        trade_supply=inputs.mining_total,
        direct_local={},
        balance_map=_sum_maps(inputs.processing_brine_balance, inputs.processing_lithium_ores_balance),
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
        balance_map=_sum_maps(inputs.refining_hydroxide_balance, inputs.refining_carbonate_balance),
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
        balance_map={},
        target_totals=inputs.cathode_total,
        known_trade=_combined_third_trade(inputs),
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


def _build_chemistry_payload(inputs: LithiumYearInputs, aggregate_display: bool):
    builder = _make_builder(inputs)
    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S1",
        post_stage="S2",
        target_stage="S3",
        source_totals=inputs.mining_total,
        trade_supply=inputs.mining_total,
        direct_local={},
        balance_map=_sum_maps(inputs.processing_brine_balance, inputs.processing_lithium_ores_balance),
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
        balance_map=_sum_maps(inputs.refining_hydroxide_balance, inputs.refining_carbonate_balance),
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
    add_stage_sink_links(
        builder,
        epsilon=EPSILON,
        source_stage="S5",
        sink_stage="S6",
        values=_positive_difference(inputs.refining_total, inputs.refining_hydroxide, inputs.refining_carbonate),
        slug="refining_other_products",
        label="Refining Other Products",
        color=SPECIAL_COLORS["refining_other"],
    )
    add_shared_pool_chem_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S5",
        post_stage="S6",
        target_stage="S7",
        source_totals=inputs.refining_hydroxide,
        trade_supply=inputs.refining_hydroxide,
        target_totals_by_category={
            "NCM": inputs.cathode_ncm,
            "NCA": inputs.cathode_nca,
        },
        balance_by_category={
            "NCM": inputs.cathode_ncm_balance,
            "NCA": inputs.cathode_nca_balance,
        },
        known_trade=inputs.trade3_hydroxide,
        source_role="Refining",
        target_role="Cathode",
        aggregate_display=aggregate_display,
    )
    add_shared_pool_chem_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S5",
        post_stage="S6",
        target_stage="S7",
        source_totals=inputs.refining_carbonate,
        trade_supply=inputs.refining_carbonate,
        target_totals_by_category={
            "LFP": inputs.cathode_lfp,
        },
        balance_by_category={
            "LFP": inputs.cathode_lfp_balance,
        },
        known_trade=inputs.trade3_carbonate,
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
        "Lithium S3 totals use the rows where both Feedstock and Product are blank in Lithium_Processing_Final.xlsx.",
        "Rows without a numeric country id, including Various and TBC, are ignored in the Sankey calculation.",
        "If a Li 2nd post trade folder is missing, the S4 trade estimate is treated as 0 and the balance formulas still run.",
        "Chemistry-related views use Lithium Hydroxide for NCM/NCA and Lithium Carbonate for LFP.",
        f"Reference quantity is set to {reference_qty:,.0f} t. Lower values enlarge nodes, and the figure height expands from the tallest full stage stack so all nodes keep the planned gap.",
        "The fixed reference node beneath S7 keeps the same visual size in every export; changing Reference Quantity only changes how many tons that box represents.",
        "Continent sorting follows the region column in ListOfreference.xlsx.",
    ]
    if view_mode != "country":
        notes.append("Refining output that is outside the hydroxide / carbonate pool is routed to the S6 special node Refining Other Products.")
    return make_payload(
        nodes=nodes,
        links=links,
        year=year,
        metal="Li",
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
    "build_app_payload",
]
