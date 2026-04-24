from __future__ import annotations

from typing import Any

from trade_flow.legacy_site.services.cobalt_data import (
    COBALT_MODE_LABELS,
    DEFAULT_COBALT_MODE,
    EPSILON,
    YEARS,
    CobaltYearInputs,
    load_year_inputs,
    resolve_cobalt_mode,
)
from trade_flow.legacy_site.services.datasets import dataset_status, load_dataset_config
from trade_flow.legacy_site.services.reference import load_reference_maps
from trade_flow.legacy_site.services.shared_sankey import (
    DEFAULT_REFERENCE_QTY,
    DEFAULT_THEME,
    SPECIAL_COLORS,
    SPECIAL_NODE_POSITIONS,
    SORT_MODES,
    STAGE_ORDER,
    THEME_MODES,
    SankeyBuilder,
    add_country_trade_section,
    add_shared_pool_chem_trade_section,
    add_stage_sink_links,
    make_payload,
)


def _make_builder(inputs: CobaltYearInputs) -> SankeyBuilder:
    config = load_dataset_config()
    id_to_name, id_to_iso3, color_map, region_map = load_reference_maps(config["referenceFile"], inputs.country_ids)
    return SankeyBuilder(id_to_name, id_to_iso3, color_map, region_map)


def _sum_country_maps(*maps: dict[int, float]) -> dict[int, float]:
    result: dict[int, float] = {}
    for mapping in maps:
        for country_id, value in mapping.items():
            result[int(country_id)] = result.get(int(country_id), 0.0) + float(value)
    return {
        country_id: value
        for country_id, value in result.items()
        if abs(value) > EPSILON
    }


def _processing_stage_country_ids(inputs: CobaltYearInputs) -> set[int]:
    return set(inputs.processing_total) | set(inputs.processing_unrelated)


def _first_post_trade_totals(inputs: CobaltYearInputs) -> dict[int, float]:
    stage_country_ids = _processing_stage_country_ids(inputs)
    return {
        country_id: float(inputs.processing_total.get(country_id, 0.0))
        + float(inputs.processing_unrelated.get(country_id, 0.0))
        + float(inputs.mining_sulphate.get(country_id, 0.0))
        for country_id in stage_country_ids
        if (
            float(inputs.processing_total.get(country_id, 0.0))
            + float(inputs.processing_unrelated.get(country_id, 0.0))
            + float(inputs.mining_sulphate.get(country_id, 0.0))
        )
        > EPSILON
    }


def _first_post_trade_direct_local(inputs: CobaltYearInputs) -> dict[int, float]:
    stage_country_ids = _processing_stage_country_ids(inputs)
    return {
        country_id: float(inputs.mining_battery.get(country_id, 0.0))
        + float(inputs.mining_sulphate.get(country_id, 0.0))
        for country_id in stage_country_ids
        if float(inputs.mining_battery.get(country_id, 0.0)) + float(inputs.mining_sulphate.get(country_id, 0.0)) > EPSILON
    }


def _second_post_trade_direct_local(inputs: CobaltYearInputs) -> dict[int, float]:
    stage_country_ids = _processing_stage_country_ids(inputs)
    return {
        country_id: float(inputs.mining_sulphate.get(country_id, 0.0))
        for country_id in stage_country_ids
        if float(inputs.mining_sulphate.get(country_id, 0.0)) > EPSILON
    }


def _refining_maps_for_mode(
    inputs: CobaltYearInputs,
    cobalt_mode: str,
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    mode = resolve_cobalt_mode(cobalt_mode)
    if mode == "max":
        return (
            inputs.refining_max,
            inputs.refining_max_balance,
            inputs.cathode_max_total_balance,
            {
                "NCM": inputs.cathode_max_ncm_balance,
                "NCA": inputs.cathode_max_nca_balance,
            },
        )
    if mode == "min":
        return (
            inputs.refining_min,
            inputs.refining_min_balance,
            inputs.cathode_min_total_balance,
            {
                "NCM": inputs.cathode_min_ncm_balance,
                "NCA": inputs.cathode_min_nca_balance,
            },
        )
    return (
        inputs.refining_mid,
        inputs.refining_mid_balance,
        inputs.cathode_mid_total_balance,
        {
            "NCM": inputs.cathode_mid_ncm_balance,
            "NCA": inputs.cathode_mid_nca_balance,
        },
    )


def _build_country_payload(inputs: CobaltYearInputs, cobalt_mode: str):
    builder = _make_builder(inputs)
    refining_total, _refining_balance, cathode_total_balance, _chem_balance = _refining_maps_for_mode(inputs, cobalt_mode)

    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S1",
        post_stage="S2",
        target_stage="S3",
        source_totals=inputs.mining_total,
        trade_supply=inputs.mining_concentrate,
        direct_local=_first_post_trade_direct_local(inputs),
        balance_map={},
        target_totals=_first_post_trade_totals(inputs),
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
        trade_supply=inputs.processing_total,
        direct_local=_second_post_trade_direct_local(inputs),
        balance_map={},
        target_totals=refining_total,
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
        source_totals=refining_total,
        trade_supply=refining_total,
        direct_local={},
        balance_map=cathode_total_balance,
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


def _build_chemistry_payload(inputs: CobaltYearInputs, cobalt_mode: str, aggregate_display: bool):
    builder = _make_builder(inputs)
    refining_total, _refining_balance, _cathode_total_balance, chem_balance = _refining_maps_for_mode(inputs, cobalt_mode)

    add_country_trade_section(
        builder,
        epsilon=EPSILON,
        source_stage="S1",
        post_stage="S2",
        target_stage="S3",
        source_totals=inputs.mining_total,
        trade_supply=inputs.mining_concentrate,
        direct_local=_first_post_trade_direct_local(inputs),
        balance_map={},
        target_totals=_first_post_trade_totals(inputs),
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
        trade_supply=inputs.processing_total,
        direct_local=_second_post_trade_direct_local(inputs),
        balance_map={},
        target_totals=refining_total,
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
        source_totals=refining_total,
        trade_supply=refining_total,
        target_totals_by_category={
            "NCM": inputs.cathode_ncm,
            "NCA": inputs.cathode_nca,
        },
        balance_by_category=chem_balance,
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
    cobalt_mode: str = DEFAULT_COBALT_MODE,
) -> dict[str, Any]:
    if year not in YEARS:
        raise ValueError(f"Unsupported year: {year}")
    if theme not in THEME_MODES:
        raise ValueError(f"Unsupported theme: {theme}")

    resolved_mode = resolve_cobalt_mode(cobalt_mode)
    inputs = load_year_inputs(year)
    if view_mode == "country":
        nodes, links = _build_country_payload(inputs, resolved_mode)
    elif view_mode == "chemistry":
        nodes, links = _build_chemistry_payload(inputs, resolved_mode, aggregate_display=False)
    elif view_mode == "chemistry_only":
        nodes, links = _build_chemistry_payload(inputs, resolved_mode, aggregate_display=True)
    else:
        raise ValueError(f"Unsupported view mode: {view_mode}")

    config = load_dataset_config()
    notes = [
        "Year range is fixed to 2020-2024 because cobalt cathode and trade files only cover those five years.",
        "Cobalt S2 and S3 explicitly add mining-side Cobalt sulphate on top of Battery related when building the mining-to-processing handoff.",
        "Cobalt S2 now uses the full Cobalt_Processing_Final country set, and its node size includes processing Unrelated plus cobalt sulphate before S3 balancing.",
        f"Refining mode is set to {COBALT_MODE_LABELS[resolved_mode]}. The site reads Max, Min, or Middle battery related rows from Cobalt_Refining_Final.xlsx accordingly.",
        "Co 2nd post trade combines the Co_282200, Co_810520, and Co_810530 folders before balancing S4.",
        "For Co S4, post-trade balancing now uses target-total fallback instead of the refining balance row so each S4 country node stays flow-conserving against its refining output plus unknown sink.",
        "Chemistry-related views split S7 into NCM and NCA while keeping S6 country-based, matching the current Ni/Li website behavior.",
        f"Reference quantity is set to {reference_qty:,.0f} t. Lower values enlarge nodes, and the figure height expands from the tallest full stage stack so all nodes keep the planned gap.",
        "The fixed reference node beneath S7 keeps the same visual size in every export; changing Reference Quantity only changes how many tons that box represents.",
        "Continent sorting follows the region column in ListOfreference.xlsx.",
    ]
    payload = make_payload(
        nodes=nodes,
        links=links,
        year=year,
        metal="Co",
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
    payload["cobaltMode"] = resolved_mode
    return payload


__all__ = [
    "DEFAULT_REFERENCE_QTY",
    "DEFAULT_THEME",
    "SPECIAL_NODE_POSITIONS",
    "SORT_MODES",
    "STAGE_ORDER",
    "YEARS",
    "build_app_payload",
]

