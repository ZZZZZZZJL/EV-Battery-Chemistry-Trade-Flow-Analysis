from __future__ import annotations

from collections import defaultdict
from typing import Any

from models import (
    EPSILON,
    BuildResult,
    LinkSpec,
    NodeSpec,
    ProductionData,
    ReferenceMaps,
    RouteSpec,
    Settings,
    TradeRecord,
)


SPECIAL_COLOR = "#8b929a"
CHEMISTRY_COLORS = {
    "NMC": "#1d4ed8",
    "NCM": "#1d4ed8",
    "NCA": "#7c3aed",
    "LFP": "#16a34a",
    "LMFP": "#0f9f6e",
    "OTHER": "#8fa5b8",
}


def _rgba(hex_color: str, opacity: float = 0.34) -> str:
    color = str(hex_color or "").lstrip("#")
    if len(color) != 6:
        return f"rgba(139, 146, 154, {opacity})"
    try:
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
    except ValueError:
        return f"rgba(139, 146, 154, {opacity})"
    return f"rgba({red}, {green}, {blue}, {opacity})"


def _slug(value: str) -> str:
    return "_".join(str(value).strip().lower().replace("/", " ").split())


class GraphBuilder:
    def __init__(
        self,
        reference: ReferenceMaps,
        fallback_labels: dict[int, str],
        country_label_mode: str = "full",
    ) -> None:
        self.reference = reference
        self.fallback_labels = fallback_labels
        self.country_label_mode = country_label_mode
        self.nodes: dict[str, NodeSpec] = {}
        self.links: list[LinkSpec] = []

    def country_name(self, country_id: int) -> str:
        return self.reference.names.get(country_id, self.fallback_labels.get(country_id, f"Country {country_id}"))

    def country_hover(self, country_id: int) -> str:
        name = self.country_name(country_id)
        iso3 = self.reference.iso3.get(country_id, "")
        return f"{name} ({iso3})" if iso3 else name

    def country_label(self, country_id: int) -> str:
        if self.country_label_mode == "iso3":
            iso3 = str(self.reference.iso3.get(country_id, "")).strip()
            if iso3:
                return iso3
        return self.country_name(country_id)

    def ensure_country(self, stage: str, country_id: int) -> str:
        key = f"{stage}:country:{country_id}"
        if key not in self.nodes:
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=self.country_label(country_id),
                color=self.reference.colors.get(country_id, "#7f8c8d"),
                kind="regular",
                hover=self.country_hover(country_id),
                region=self.reference.regions.get(country_id, "Unknown") or "Unknown",
            )
        return key

    def ensure_country_chemistry(self, stage: str, country_id: int, chemistry: str) -> str:
        key = f"{stage}:chem:{country_id}:{_slug(chemistry)}"
        if key not in self.nodes:
            country = self.country_label(country_id)
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=f"{country} / {chemistry}",
                color=self.reference.colors.get(country_id, "#7f8c8d"),
                kind="regular",
                hover=f"{self.country_hover(country_id)} / {chemistry}",
                region=self.reference.regions.get(country_id, "Unknown") or "Unknown",
            )
        return key

    def ensure_global_chemistry(self, stage: str, chemistry: str) -> str:
        normalized = str(chemistry).strip().upper()
        key = f"{stage}:chemistry:{_slug(normalized)}"
        if key not in self.nodes:
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=normalized,
                color=CHEMISTRY_COLORS.get(normalized, CHEMISTRY_COLORS["OTHER"]),
                kind="regular",
                hover=normalized,
                region="Unknown",
            )
        return key

    def ensure_special(self, stage: str, slug: str, label: str, kind: str) -> str:
        key = f"{stage}:special:{slug}"
        if key not in self.nodes:
            self.nodes[key] = NodeSpec(
                key=key,
                stage=stage,
                label=label,
                color=SPECIAL_COLOR,
                kind=kind,
                hover=label,
                region="Unknown",
            )
        return key

    def add_link(self, source: str, target: str, value: float) -> None:
        if value <= EPSILON:
            return
        source_color = self.nodes[source].color if source in self.nodes else SPECIAL_COLOR
        self.links.append(
            LinkSpec(
                source=source,
                target=target,
                value=float(value),
                color=_rgba(source_color),
            )
        )


def _classification(exporter: int, importer: int, source_ids: set[int], target_ids: set[int]) -> str:
    source_producer = exporter in source_ids
    target_producer = importer in target_ids
    if source_producer and target_producer:
        return "producer_to_producer"
    if source_producer and not target_producer:
        return "producer_to_non_target"
    if not source_producer and target_producer:
        return "non_source_to_producer"
    return "non_source_to_non_target"


def _prepare_trade_records(
    records: list[TradeRecord],
    source_totals: dict[int, float],
    target_totals: dict[int, float],
) -> None:
    source_ids = {country_id for country_id, value in source_totals.items() if value > EPSILON}
    target_ids = {country_id for country_id, value in target_totals.items() if value > EPSILON}
    exporter_totals: dict[int, float] = defaultdict(float)
    for record in records:
        record.classification = _classification(record.exporter_id, record.importer_id, source_ids, target_ids)
        record.converted_quantity_before_scaling = (
            record.raw_quantity_tonnes * record.manual_conversion_factor
        )
        exporter_totals[record.exporter_id] += record.converted_quantity_before_scaling

    multipliers: dict[int, float] = {}
    for exporter_id in source_ids:
        converted_total = exporter_totals.get(exporter_id, 0.0)
        available = float(source_totals.get(exporter_id, 0.0))
        multipliers[exporter_id] = min(1.0, available / converted_total) if converted_total > EPSILON else 1.0

    for record in records:
        is_source_producer = record.exporter_id in source_ids
        record.available_source_production = float(source_totals.get(record.exporter_id, 0.0))
        record.exporter_total_before_scaling = float(exporter_totals.get(record.exporter_id, 0.0))
        record.production_scaling_multiplier = multipliers.get(record.exporter_id, 1.0)
        record.effective_conversion_factor = (
            record.manual_conversion_factor * record.production_scaling_multiplier
        )
        record.final_trade_quantity_tonnes = (
            record.raw_quantity_tonnes * record.effective_conversion_factor
        )
        record.included_in_sankey = (
            record.classification != "non_source_to_non_target"
            and record.final_trade_quantity_tonnes > EPSILON
        )
        if record.classification == "non_source_to_non_target":
            record.adjustment_reason = "ignored: no upstream production and no downstream production"
        elif not is_source_producer:
            record.adjustment_reason = "non-source exporter; preserved without production scaling"
        elif record.production_scaling_multiplier < 1.0 - EPSILON:
            record.adjustment_reason = "production cap applied to exporter total"
        else:
            record.adjustment_reason = "manual factor retained; exporter production cap not binding"


def _chemistry_shares(
    production: ProductionData,
    stage: str,
    country_id: int | None,
) -> dict[str, float]:
    source = production.stage_chemistry.get(stage, {})
    values = {
        chemistry: float(mapping.get(country_id, 0.0))
        for chemistry, mapping in source.items()
        if country_id is not None and float(mapping.get(country_id, 0.0)) > EPSILON
    }
    total = sum(values.values())
    if total <= EPSILON:
        values = {chemistry: sum(map(float, mapping.values())) for chemistry, mapping in source.items()}
        total = sum(values.values())
    return {chemistry: value / total for chemistry, value in values.items() if total > EPSILON}


def _apply_chemistry_weighted_factors(
    records: list[TradeRecord],
    transition_source: str,
    transition_target: str,
    settings: Settings,
    production: ProductionData,
) -> None:
    factors = settings.chemistry_conversion_factors
    if not factors or not ({transition_source, transition_target} & {"cathode", "battery"}):
        return
    for record in records:
        if transition_source == "cathode":
            stage = "cathode"
            country_id = record.exporter_id
            basis = "exporter cathode chemistry share"
        elif transition_target == "cathode":
            stage = "cathode"
            country_id = record.importer_id
            basis = "importer cathode chemistry share"
        else:
            stage = transition_target
            country_id = record.importer_id
            basis = f"importer {stage} chemistry share"
        shares = _chemistry_shares(production, stage, country_id)
        weighted = 0.0
        used = 0.0
        for chemistry, share in shares.items():
            lookup = "LFP" if chemistry == "LMFP" and chemistry not in factors else chemistry
            if lookup in factors:
                weighted += share * factors[lookup]
                used += share
        if used > EPSILON:
            record.manual_conversion_factor = weighted / used
            record.chemistry_factor_basis = basis
            record.chemistry_factor_detail = "; ".join(
                f"{chemistry}:share={share:.8g},factor={factors.get('LFP' if chemistry == 'LMFP' and chemistry not in factors else chemistry, 'NA')}"
                for chemistry, share in sorted(shares.items())
            )


def _prepare_trade_only_records(
    records: list[TradeRecord],
    source_totals: dict[int, float],
    target_totals: dict[int, float],
) -> None:
    source_ids = {country_id for country_id, value in source_totals.items() if value > EPSILON}
    target_ids = {country_id for country_id, value in target_totals.items() if value > EPSILON}
    exporter_totals: dict[int, float] = defaultdict(float)
    for record in records:
        record.classification = _classification(record.exporter_id, record.importer_id, source_ids, target_ids)
        record.converted_quantity_before_scaling = (
            record.raw_quantity_tonnes * record.manual_conversion_factor
        )
        exporter_totals[record.exporter_id] += record.converted_quantity_before_scaling
    for record in records:
        record.available_source_production = 0.0
        record.exporter_total_before_scaling = float(exporter_totals.get(record.exporter_id, 0.0))
        record.production_scaling_multiplier = 1.0
        record.effective_conversion_factor = record.manual_conversion_factor
        record.final_trade_quantity_tonnes = record.converted_quantity_before_scaling
        record.included_in_sankey = (
            record.classification != "non_source_to_non_target"
            and record.final_trade_quantity_tonnes > EPSILON
        )
        if record.classification == "non_source_to_non_target":
            record.adjustment_reason = "ignored: no upstream production and no downstream production"
        else:
            record.adjustment_reason = "trade-only mode; manual factor retained without production scaling"


def _chemistry_values(
    production: ProductionData,
    country_id: int,
    target_total: float,
    feedstock_totals: dict[str, float] | None = None,
    stage_name: str = "cathode",
) -> dict[str, float]:
    production_total = float(production.totals.get(stage_name, {}).get(country_id, 0.0))
    chemistry_source = production.stage_chemistry.get(stage_name, {})
    if not chemistry_source and stage_name == "cathode":
        chemistry_source = production.cathode_chemistry
    production_values = {
        str(chemistry).strip().upper(): float(mapping.get(country_id, 0.0))
        for chemistry, mapping in chemistry_source.items()
        if float(mapping.get(country_id, 0.0)) > EPSILON
    }
    chemistry_total = sum(production_values.values())
    tolerance = max(1e-6, abs(production_total) * 1e-8)
    if chemistry_total > production_total + tolerance:
        raise ValueError(
            f"Cathode chemistry exceeds Product=Total for country id {country_id}: "
            f"chemistry={chemistry_total}, total={production_total}"
        )
    residual = production_total - chemistry_total
    if residual > tolerance:
        production_values["OTHER"] = production_values.get("OTHER", 0.0) + residual
    elif abs(residual) <= tolerance and chemistry_total > EPSILON:
        scale = production_total / chemistry_total
        production_values = {
            chemistry: value * scale for chemistry, value in production_values.items()
        }
    if not production_values and production_total > EPSILON:
        production_values["OTHER"] = production_total
    if production_total <= EPSILON:
        return {"OTHER": target_total} if target_total > EPSILON else {}
    base_values = {
        chemistry: target_total * value / production_total
        for chemistry, value in production_values.items()
        if target_total * value / production_total > EPSILON
    }
    if stage_name == "battery" and feedstock_totals and "LMFP" in feedstock_totals:
        chemistry_input_total = sum(
            value for chemistry, value in feedstock_totals.items()
            if chemistry in {"LFP", "LMFP", "NMC", "NCM", "NCA"}
        )
        if chemistry_input_total > EPSILON:
            other_value = target_total * feedstock_totals["LMFP"] / chemistry_input_total
            remaining = max(target_total - other_value, 0.0)
            base_total = sum(base_values.values())
            result = {
                chemistry: remaining * value / base_total
                for chemistry, value in base_values.items()
                if base_total > EPSILON and remaining * value / base_total > EPSILON
            }
            if other_value > EPSILON:
                result["OTHER"] = other_value
            return result
    if not feedstock_totals:
        return base_values

    affinity = {
        "LITHIUM CARBONATE": {
            "LFP": 1.0, "LMFP": 1.0, "NMC": 0.25, "NCM": 0.25, "NCA": 0.25,
        },
        "LITHIUM HYDROXIDE": {
            "NMC": 1.0, "NCM": 1.0, "NCA": 1.0, "LFP": 0.25, "LMFP": 0.25,
        },
    }
    scores: dict[str, float] = defaultdict(float)
    for product, feedstock_value in feedstock_totals.items():
        weights = affinity.get(str(product).strip().upper())
        if not weights or feedstock_value <= EPSILON:
            continue
        weighted = {
            chemistry: value * weights.get(chemistry, 0.0)
            for chemistry, value in base_values.items()
            if weights.get(chemistry, 0.0) > 0.0
        }
        weighted_total = sum(weighted.values())
        if weighted_total <= EPSILON:
            continue
        for chemistry, value in weighted.items():
            scores[chemistry] += float(feedstock_value) * value / weighted_total
    score_total = sum(scores.values())
    if score_total <= EPSILON:
        return base_values
    return {
        chemistry: target_total * score / score_total
        for chemistry, score in scores.items()
        if target_total * score / score_total > EPSILON
    }


def _add_target_output(
    graph: GraphBuilder,
    *,
    post_key: str,
    target_stage_key: str,
    target_stage_name: str,
    country_id: int,
    target_total: float,
    settings: Settings,
    production: ProductionData,
    feedstock_totals: dict[str, float] | None = None,
) -> None:
    split_target = (
        settings.cathode_view != "country"
        and (
            target_stage_name == "battery"
            or (target_stage_name == "cathode" and settings.chemistry_stage_scope == "both")
        )
    )
    if not split_target:
        target_key = graph.ensure_country(target_stage_key, country_id)
        graph.add_link(post_key, target_key, target_total)
        return
    chemistry_values = _chemistry_values(
        production,
        country_id,
        target_total,
        feedstock_totals=feedstock_totals,
        stage_name=target_stage_name,
    )
    for chemistry, value in chemistry_values.items():
        if settings.cathode_view == "country_chemistry":
            target_key = graph.ensure_country_chemistry(target_stage_key, country_id, chemistry)
        else:
            target_key = graph.ensure_global_chemistry(target_stage_key, chemistry)
        graph.add_link(post_key, target_key, value)


def _add_source_output(
    graph: GraphBuilder,
    *,
    source_stage_key: str,
    source_stage_name: str,
    country_id: int,
    target_key: str,
    value: float,
    settings: Settings,
    production: ProductionData,
) -> None:
    split_source = (
        source_stage_name == "cathode"
        and settings.cathode_view != "country"
        and settings.chemistry_stage_scope == "both"
    )
    if not split_source:
        graph.add_link(graph.ensure_country(source_stage_key, country_id), target_key, value)
        return
    for chemistry, chemistry_value in _chemistry_values(
        production, country_id, value, stage_name="cathode"
    ).items():
        if settings.cathode_view == "country_chemistry":
            source_key = graph.ensure_country_chemistry(source_stage_key, country_id, chemistry)
        else:
            source_key = graph.ensure_global_chemistry(source_stage_key, chemistry)
        graph.add_link(source_key, target_key, chemistry_value)


def _contained_chemistry_components(
    record: TradeRecord,
    production: ProductionData,
    settings: Settings,
) -> dict[str, float]:
    shares = _chemistry_shares(production, "cathode", record.exporter_id)
    if not shares:
        return {}
    weighted = {}
    for chemistry, share in shares.items():
        lookup = "LFP" if chemistry == "LMFP" and settings.merge_lmfp_into_lfp else chemistry
        factor = settings.chemistry_conversion_factors.get(lookup, record.manual_conversion_factor)
        weighted[chemistry] = share * factor
    total = sum(weighted.values())
    return {
        chemistry: record.final_trade_quantity_tonnes * weight / total
        for chemistry, weight in weighted.items()
        if total > EPSILON
    }


def _conversion_row(
    settings: Settings,
    route: RouteSpec,
    transition_label: str,
    record: TradeRecord,
    graph: GraphBuilder,
) -> dict[str, Any]:
    return {
        "metal": settings.metal,
        "year": settings.year,
        "route": route.key,
        "transition": record.transition,
        "transition_label": transition_label,
        "trade_data_direction": "Import data: reporter/importer <- partner/exporter",
        "hs_code": record.hs_code,
        "target_product": record.target_product,
        "chemistry_factor_basis": record.chemistry_factor_basis,
        "chemistry_factor_detail": record.chemistry_factor_detail,
        "importer_id": record.importer_id,
        "importer_name": graph.country_name(record.importer_id),
        "exporter_id": record.exporter_id,
        "exporter_name": graph.country_name(record.exporter_id),
        "classification": record.classification,
        "raw_quantity_tonnes": record.raw_quantity_tonnes,
        "manual_conversion_factor": record.manual_conversion_factor,
        "configured_conversion_factor": record.configured_conversion_factor,
        "converted_quantity_before_scaling": record.converted_quantity_before_scaling,
        "available_source_production": record.available_source_production,
        "exporter_total_before_scaling": record.exporter_total_before_scaling,
        "production_scaling_multiplier": record.production_scaling_multiplier,
        "effective_conversion_factor": record.effective_conversion_factor,
        "final_trade_quantity_tonnes": record.final_trade_quantity_tonnes,
        "included_in_sankey": record.included_in_sankey,
        "adjustment_reason": record.adjustment_reason,
        "source_files": " | ".join(record.source_files),
    }


def _build_production_flow_graph(
    settings: Settings,
    route: RouteSpec,
    production: ProductionData,
    reference: ReferenceMaps,
    trade_by_transition: dict[str, list[TradeRecord]],
) -> BuildResult:
    graph = GraphBuilder(reference, production.labels, settings.country_label_mode)
    conversion_rows: list[dict[str, Any]] = []
    balance_rows: list[dict[str, Any]] = []

    for transition in route.transitions:
        source_totals = production.totals[transition.source_stage]
        target_totals = production.totals[transition.target_stage]
        source_ids = set(source_totals)
        target_ids = set(target_totals)
        records = trade_by_transition.get(transition.key, [])
        _apply_chemistry_weighted_factors(
            records, transition.source_stage, transition.target_stage, settings, production
        )
        _prepare_trade_records(records, source_totals, target_totals)

        source_stage_key = f"P:{transition.source_stage}"
        post_stage_key = f"T:{transition.key}"
        target_stage_key = f"P:{transition.target_stage}"
        source_label = next(stage.label for stage in route.production_stages if stage.key == transition.source_stage)
        target_label = next(stage.label for stage in route.production_stages if stage.key == transition.target_stage)

        producer_to_non_target = graph.ensure_special(
            post_stage_key,
            f"{transition.key}_non_target",
            f"{source_label} to Non-{target_label} Countries",
            "sink_special",
        )
        from_non_source = graph.ensure_special(
            source_stage_key,
            f"{transition.key}_non_source",
            f"From Non-{source_label} Countries",
            "source_special",
        )
        unknown_source = graph.ensure_special(
            source_stage_key,
            f"{transition.key}_unknown_source",
            f"Unknown {source_label} Source",
            "source_special",
        )
        unknown_target = graph.ensure_special(
            target_stage_key,
            f"{transition.key}_unknown_target",
            f"{source_label} to Unknown Destination",
            "sink_special",
        )

        export_by_country: dict[int, float] = defaultdict(float)
        import_by_country: dict[int, float] = defaultdict(float)
        pp_import_by_country: dict[int, float] = defaultdict(float)
        np_import_by_country: dict[int, float] = defaultdict(float)
        pn_export_by_country: dict[int, float] = defaultdict(float)
        feedstock_by_country: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for record in records:
            conversion_rows.append(
                _conversion_row(settings, route, transition.label, record, graph)
            )
            if not record.included_in_sankey:
                continue
            value = record.final_trade_quantity_tonnes
            if record.classification == "producer_to_producer":
                post_key = graph.ensure_country(post_stage_key, record.importer_id)
                _add_source_output(
                    graph, source_stage_key=source_stage_key,
                    source_stage_name=transition.source_stage, country_id=record.exporter_id,
                    target_key=post_key, value=value, settings=settings, production=production,
                )
                export_by_country[record.exporter_id] += value
                import_by_country[record.importer_id] += value
                pp_import_by_country[record.importer_id] += value
                if record.target_product:
                    feedstock_by_country[record.importer_id][record.target_product] += value
                if transition.source_stage == "cathode":
                    for chemistry, component in _contained_chemistry_components(record, production, settings).items():
                        feedstock_by_country[record.importer_id][chemistry] += component
            elif record.classification == "producer_to_non_target":
                _add_source_output(
                    graph, source_stage_key=source_stage_key,
                    source_stage_name=transition.source_stage, country_id=record.exporter_id,
                    target_key=producer_to_non_target, value=value, settings=settings, production=production,
                )
                export_by_country[record.exporter_id] += value
                pn_export_by_country[record.exporter_id] += value
            elif record.classification == "non_source_to_producer":
                post_key = graph.ensure_country(post_stage_key, record.importer_id)
                graph.add_link(from_non_source, post_key, value)
                import_by_country[record.importer_id] += value
                np_import_by_country[record.importer_id] += value
                if record.target_product:
                    feedstock_by_country[record.importer_id][record.target_product] += value
                if transition.source_stage == "cathode":
                    for chemistry, component in _contained_chemistry_components(record, production, settings).items():
                        feedstock_by_country[record.importer_id][chemistry] += component

        domestic: dict[int, float] = defaultdict(float)
        untraded_to_non_target: dict[int, float] = defaultdict(float)
        for country_id, source_total in source_totals.items():
            remainder = max(float(source_total) - export_by_country.get(country_id, 0.0), 0.0)
            if remainder <= EPSILON:
                continue
            if country_id in target_ids:
                post_key = graph.ensure_country(post_stage_key, country_id)
                _add_source_output(
                    graph, source_stage_key=source_stage_key,
                    source_stage_name=transition.source_stage, country_id=country_id,
                    target_key=post_key, value=remainder, settings=settings, production=production,
                )
                domestic[country_id] += remainder
                if transition.source_stage == "cathode":
                    for chemistry, share in _chemistry_shares(production, "cathode", country_id).items():
                        feedstock_by_country[country_id][chemistry] += remainder * share
            else:
                _add_source_output(
                    graph, source_stage_key=source_stage_key,
                    source_stage_name=transition.source_stage, country_id=country_id,
                    target_key=producer_to_non_target, value=remainder, settings=settings, production=production,
                )
                untraded_to_non_target[country_id] += remainder

        unknown_source_by_country: dict[int, float] = defaultdict(float)
        excess_by_country: dict[int, float] = defaultdict(float)
        for country_id, target_total in target_totals.items():
            post_key = graph.ensure_country(post_stage_key, country_id)
            known_input = import_by_country.get(country_id, 0.0) + domestic.get(country_id, 0.0)
            gap = max(float(target_total) - known_input, 0.0)
            excess = max(known_input - float(target_total), 0.0)
            if gap > EPSILON:
                graph.add_link(unknown_source, post_key, gap)
                unknown_source_by_country[country_id] = gap
            _add_target_output(
                graph,
                post_key=post_key,
                target_stage_key=target_stage_key,
                target_stage_name=transition.target_stage,
                country_id=country_id,
                target_total=float(target_total),
                settings=settings,
                production=production,
                feedstock_totals=dict(feedstock_by_country.get(country_id, {})),
            )
            if excess > EPSILON:
                graph.add_link(post_key, unknown_target, excess)
                excess_by_country[country_id] = excess

        for country_id in sorted(source_ids | target_ids):
            source_total = float(source_totals.get(country_id, 0.0))
            target_total = float(target_totals.get(country_id, 0.0))
            exports = export_by_country.get(country_id, 0.0)
            domestic_value = domestic.get(country_id, 0.0)
            untraded_value = untraded_to_non_target.get(country_id, 0.0)
            imports = import_by_country.get(country_id, 0.0)
            unknown_value = unknown_source_by_country.get(country_id, 0.0)
            excess_value = excess_by_country.get(country_id, 0.0)
            source_residual = source_total - exports - domestic_value - untraded_value
            post_residual = imports + domestic_value + unknown_value - target_total - excess_value
            balance_rows.append(
                {
                    "metal": settings.metal,
                    "year": settings.year,
                    "route": route.key,
                    "node_basis_mode": "production",
                    "transition": transition.key,
                    "transition_label": transition.label,
                    "country_id": country_id,
                    "country_name": graph.country_name(country_id),
                    "source_stage": transition.source_stage,
                    "target_stage": transition.target_stage,
                    "source_production": source_total,
                    "target_production": target_total,
                    "trade_exports": exports,
                    "trade_imports": imports,
                    "producer_to_producer_imports": pp_import_by_country.get(country_id, 0.0),
                    "from_non_source_imports": np_import_by_country.get(country_id, 0.0),
                    "trade_exports_to_non_target": pn_export_by_country.get(country_id, 0.0),
                    "domestic_flow": domestic_value,
                    "untraded_production_to_non_target": untraded_value,
                    "unknown_source": unknown_value,
                    "excess_to_unknown_destination": excess_value,
                    "source_balance_residual": source_residual,
                    "post_trade_balance_residual": post_residual,
                }
            )

    return BuildResult(
        nodes=graph.nodes,
        links=tuple(graph.links),
        conversion_rows=tuple(conversion_rows),
        balance_rows=tuple(balance_rows),
        stage_rows=tuple(),
    )


def _build_trade_only_flow_graph(
    settings: Settings,
    route: RouteSpec,
    production: ProductionData,
    reference: ReferenceMaps,
    trade_by_transition: dict[str, list[TradeRecord]],
) -> BuildResult:
    graph = GraphBuilder(reference, production.labels, settings.country_label_mode)
    stage_specs = list(route.production_stages)
    stage_index = {stage.key: index for index, stage in enumerate(stage_specs)}
    memberships = [set(production.totals[stage.key]) for stage in stage_specs]
    incoming_trade: dict[tuple[int, int], float] = defaultdict(float)
    outgoing_trade: dict[tuple[int, int], float] = defaultdict(float)
    conversion_rows: list[dict[str, Any]] = []

    pp_imports: dict[tuple[int, int], float] = defaultdict(float)
    np_imports: dict[tuple[int, int], float] = defaultdict(float)
    pn_exports: dict[tuple[int, int], float] = defaultdict(float)

    for transition_index, transition in enumerate(route.transitions):
        records = trade_by_transition.get(transition.key, [])
        _apply_chemistry_weighted_factors(
            records, transition.source_stage, transition.target_stage, settings, production
        )
        _prepare_trade_only_records(
            records,
            production.totals[transition.source_stage],
            production.totals[transition.target_stage],
        )
        for record in records:
            conversion_rows.append(
                _conversion_row(settings, route, transition.label, record, graph)
            )
            if not record.included_in_sankey:
                continue
            value = record.final_trade_quantity_tonnes
            if record.classification in {"producer_to_producer", "producer_to_non_target"}:
                outgoing_trade[(transition_index, record.exporter_id)] += value
            if record.classification in {"producer_to_producer", "non_source_to_producer"}:
                incoming_trade[(transition_index + 1, record.importer_id)] += value
            if record.classification == "producer_to_producer":
                pp_imports[(transition_index, record.importer_id)] += value
            elif record.classification == "non_source_to_producer":
                np_imports[(transition_index, record.importer_id)] += value
            elif record.classification == "producer_to_non_target":
                pn_exports[(transition_index, record.exporter_id)] += value

    domestic: dict[tuple[int, int], float] = defaultdict(float)
    unknown_source: dict[tuple[int, int], float] = defaultdict(float)
    unknown_destination: dict[tuple[int, int], float] = defaultdict(float)
    intrinsic_source: dict[tuple[int, int], float] = defaultdict(float)
    terminal_absorption: dict[tuple[int, int], float] = defaultdict(float)
    node_size: dict[tuple[int, int], float] = defaultdict(float)
    material_residual: dict[tuple[int, int], float] = defaultdict(float)

    all_country_ids = sorted(set().union(*memberships))
    for country_id in all_country_ids:
        index = 0
        while index < len(stage_specs):
            if country_id not in memberships[index]:
                index += 1
                continue
            start = index
            while index + 1 < len(stage_specs) and country_id in memberships[index + 1]:
                index += 1
            end = index

            cumulative_deficit = 0.0
            maximum_deficit = 0.0
            for stage_pos in range(start, end + 1):
                cumulative_deficit += (
                    outgoing_trade.get((stage_pos, country_id), 0.0)
                    - incoming_trade.get((stage_pos, country_id), 0.0)
                )
                maximum_deficit = max(maximum_deficit, cumulative_deficit)
            boundary_input = max(0.0, maximum_deficit)
            if start == 0:
                intrinsic_source[(start, country_id)] = boundary_input
            else:
                unknown_source[(start, country_id)] = boundary_input

            running_input = boundary_input
            for stage_pos in range(start, end + 1):
                trade_in = incoming_trade.get((stage_pos, country_id), 0.0)
                trade_out = outgoing_trade.get((stage_pos, country_id), 0.0)
                input_total = trade_in + running_input
                if stage_pos < end:
                    downstream_domestic = max(0.0, input_total - trade_out)
                    domestic[(stage_pos, country_id)] = downstream_domestic
                    output_total = trade_out + downstream_domestic
                    running_input = downstream_domestic
                else:
                    boundary_output = max(0.0, input_total - trade_out)
                    if end == len(stage_specs) - 1:
                        terminal_absorption[(end, country_id)] = boundary_output
                    else:
                        unknown_destination[(end, country_id)] = boundary_output
                    output_total = trade_out + boundary_output
                node_size[(stage_pos, country_id)] = max(input_total, output_total)
                material_residual[(stage_pos, country_id)] = input_total - output_total
            index += 1

    post_incoming: dict[tuple[int, int], float] = defaultdict(float)
    post_feedstocks: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for transition_index, transition in enumerate(route.transitions):
        source_stage_key = f"P:{transition.source_stage}"
        post_stage_key = f"T:{transition.key}"
        source_label = stage_specs[transition_index].label
        target_label = stage_specs[transition_index + 1].label
        non_target_key = graph.ensure_special(
            post_stage_key,
            f"{transition.key}_non_target",
            f"{source_label} to Non-{target_label} Countries",
            "sink_special",
        )
        non_source_key = graph.ensure_special(
            source_stage_key,
            f"{transition.key}_non_source",
            f"From Non-{source_label} Countries",
            "source_special",
        )
        unknown_source_key = graph.ensure_special(
            source_stage_key,
            f"{transition.key}_unknown_source",
            f"Unknown {source_label} Source",
            "source_special",
        )
        unknown_destination_key = graph.ensure_special(
            post_stage_key,
            f"{transition.key}_unknown_destination",
            f"{source_label} to Unknown Destination",
            "sink_special",
        )

        for record in trade_by_transition.get(transition.key, []):
            if not record.included_in_sankey:
                continue
            value = record.final_trade_quantity_tonnes
            if record.classification == "producer_to_producer":
                post_key = graph.ensure_country(post_stage_key, record.importer_id)
                _add_source_output(
                    graph, source_stage_key=source_stage_key,
                    source_stage_name=transition.source_stage, country_id=record.exporter_id,
                    target_key=post_key, value=value, settings=settings, production=production,
                )
                post_incoming[(transition_index, record.importer_id)] += value
                if record.target_product:
                    post_feedstocks[(transition_index, record.importer_id)][record.target_product] += value
                if transition.source_stage == "cathode":
                    for chemistry, component in _contained_chemistry_components(record, production, settings).items():
                        post_feedstocks[(transition_index, record.importer_id)][chemistry] += component
            elif record.classification == "producer_to_non_target":
                _add_source_output(
                    graph, source_stage_key=source_stage_key,
                    source_stage_name=transition.source_stage, country_id=record.exporter_id,
                    target_key=non_target_key, value=value, settings=settings, production=production,
                )
            elif record.classification == "non_source_to_producer":
                post_key = graph.ensure_country(post_stage_key, record.importer_id)
                graph.add_link(non_source_key, post_key, value)
                post_incoming[(transition_index, record.importer_id)] += value
                if record.target_product:
                    post_feedstocks[(transition_index, record.importer_id)][record.target_product] += value
                if transition.source_stage == "cathode":
                    for chemistry, component in _contained_chemistry_components(record, production, settings).items():
                        post_feedstocks[(transition_index, record.importer_id)][chemistry] += component

        for country_id in memberships[transition_index] & memberships[transition_index + 1]:
            value = domestic.get((transition_index, country_id), 0.0)
            if value <= EPSILON:
                continue
            post_key = graph.ensure_country(post_stage_key, country_id)
            _add_source_output(
                graph, source_stage_key=source_stage_key,
                source_stage_name=transition.source_stage, country_id=country_id,
                target_key=post_key, value=value, settings=settings, production=production,
            )
            post_incoming[(transition_index, country_id)] += value
            if transition.source_stage == "cathode":
                for chemistry, share in _chemistry_shares(production, "cathode", country_id).items():
                    post_feedstocks[(transition_index, country_id)][chemistry] += value * share

        for country_id in memberships[transition_index + 1]:
            value = unknown_source.get((transition_index + 1, country_id), 0.0)
            if value <= EPSILON:
                continue
            post_key = graph.ensure_country(post_stage_key, country_id)
            graph.add_link(unknown_source_key, post_key, value)
            post_incoming[(transition_index, country_id)] += value

        for country_id in memberships[transition_index]:
            value = unknown_destination.get((transition_index, country_id), 0.0)
            if value <= EPSILON:
                continue
            _add_source_output(
                graph, source_stage_key=source_stage_key,
                source_stage_name=transition.source_stage, country_id=country_id,
                target_key=unknown_destination_key, value=value, settings=settings, production=production,
            )

        for country_id in memberships[transition_index + 1]:
            value = post_incoming.get((transition_index, country_id), 0.0)
            if value <= EPSILON:
                continue
            post_key = graph.ensure_country(post_stage_key, country_id)
            _add_target_output(
                graph,
                post_key=post_key,
                target_stage_key=f"P:{transition.target_stage}",
                target_stage_name=transition.target_stage,
                country_id=country_id,
                target_total=value,
                settings=settings,
                production=production,
                feedstock_totals=dict(post_feedstocks.get((transition_index, country_id), {})),
            )

    stage_rows: list[dict[str, Any]] = []
    for stage_pos, stage in enumerate(stage_specs):
        for country_id in sorted(memberships[stage_pos]):
            trade_in = incoming_trade.get((stage_pos, country_id), 0.0)
            trade_out = outgoing_trade.get((stage_pos, country_id), 0.0)
            domestic_in = domestic.get((stage_pos - 1, country_id), 0.0) if stage_pos > 0 else 0.0
            domestic_out = domestic.get((stage_pos, country_id), 0.0) if stage_pos < len(stage_specs) - 1 else 0.0
            unknown_in = unknown_source.get((stage_pos, country_id), 0.0)
            unknown_out = unknown_destination.get((stage_pos, country_id), 0.0)
            intrinsic = intrinsic_source.get((stage_pos, country_id), 0.0)
            terminal = terminal_absorption.get((stage_pos, country_id), 0.0)
            stage_rows.append(
                {
                    "metal": settings.metal,
                    "year": settings.year,
                    "route": route.key,
                    "node_basis_mode": "trade_only",
                    "country_id": country_id,
                    "country_name": graph.country_name(country_id),
                    "production_stage": stage.key,
                    "is_in_stage_list": True,
                    "trade_import": trade_in,
                    "trade_export": trade_out,
                    "domestic_from_upstream": domestic_in,
                    "domestic_to_downstream": domestic_out,
                    "unknown_source": unknown_in,
                    "unknown_destination": unknown_out,
                    "intrinsic_chain_source": intrinsic,
                    "terminal_chain_absorption": terminal,
                    "node_size": node_size.get((stage_pos, country_id), 0.0),
                    "material_balance_residual": material_residual.get((stage_pos, country_id), 0.0),
                }
            )

    stage_row_map = {
        (stage_index[row["production_stage"]], int(row["country_id"])): row
        for row in stage_rows
    }
    balance_rows: list[dict[str, Any]] = []
    for transition_index, transition in enumerate(route.transitions):
        source_ids = memberships[transition_index]
        target_ids = memberships[transition_index + 1]
        for country_id in sorted(source_ids | target_ids):
            source_row = stage_row_map.get((transition_index, country_id), {})
            target_row = stage_row_map.get((transition_index + 1, country_id), {})
            post_value = post_incoming.get((transition_index, country_id), 0.0)
            balance_rows.append(
                {
                    "metal": settings.metal,
                    "year": settings.year,
                    "route": route.key,
                    "node_basis_mode": "trade_only",
                    "transition": transition.key,
                    "transition_label": transition.label,
                    "country_id": country_id,
                    "country_name": graph.country_name(country_id),
                    "source_stage": transition.source_stage,
                    "target_stage": transition.target_stage,
                    "source_production": source_row.get("node_size", 0.0),
                    "target_production": target_row.get("node_size", 0.0),
                    "trade_exports": outgoing_trade.get((transition_index, country_id), 0.0),
                    "trade_imports": incoming_trade.get((transition_index + 1, country_id), 0.0),
                    "producer_to_producer_imports": pp_imports.get((transition_index, country_id), 0.0),
                    "from_non_source_imports": np_imports.get((transition_index, country_id), 0.0),
                    "trade_exports_to_non_target": pn_exports.get((transition_index, country_id), 0.0),
                    "domestic_flow": domestic.get((transition_index, country_id), 0.0),
                    "untraded_production_to_non_target": 0.0,
                    "unknown_source": unknown_source.get((transition_index + 1, country_id), 0.0),
                    "excess_to_unknown_destination": unknown_destination.get((transition_index, country_id), 0.0),
                    "source_balance_residual": source_row.get("material_balance_residual", 0.0),
                    "post_trade_balance_residual": post_value - post_value,
                }
            )

    return BuildResult(
        nodes=graph.nodes,
        links=tuple(graph.links),
        conversion_rows=tuple(conversion_rows),
        balance_rows=tuple(balance_rows),
        stage_rows=tuple(stage_rows),
    )


def build_flow_graph(
    settings: Settings,
    route: RouteSpec,
    production: ProductionData,
    reference: ReferenceMaps,
    trade_by_transition: dict[str, list[TradeRecord]],
) -> BuildResult:
    if settings.use_production_data:
        return _build_production_flow_graph(
            settings,
            route,
            production,
            reference,
            trade_by_transition,
        )
    return _build_trade_only_flow_graph(
        settings,
        route,
        production,
        reference,
        trade_by_transition,
    )
