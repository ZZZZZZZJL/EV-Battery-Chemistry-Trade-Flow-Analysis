from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from flow_builder import (  # noqa: E402
    GraphBuilder,
    _apply_chemistry_weighted_factors,
    _chemistry_values,
    _prepare_trade_records,
    build_flow_graph,
)
from loaders import load_production, load_trade_records, normalize_metal  # noqa: E402
from models import (  # noqa: E402
    LinkSpec,
    NodeSpec,
    ProductionData,
    ProductionStage,
    ReferenceMaps,
    RouteSpec,
    Settings,
    TradeRecord,
    TransitionSpec,
)
from renderer import make_figure  # noqa: E402
from routes import ROUTES, display_stages, route_for, route_from_options  # noqa: E402
from pipeline import _production_source_tag  # noqa: E402


def settings(**overrides) -> Settings:
    values = {
        "metal": "Ni",
        "year": 2024,
        "route": "full",
        "merge_processing_refining": False,
        "show_pcam": False,
        "show_battery": False,
        "cathode_view": "country",
        "chemistry_stage_scope": "both",
        "merge_lmfp_into_lfp": True,
        "shared_hs_trade_owner": "downstream",
        "chemistry_conversion_factors": {},
        "use_production_data": True,
        "production_source": "benchmark",
        "production_sheets": None,
        "production_root": Path("production"),
        "trade_root": Path("trade"),
        "reference_file": Path("reference.xlsx"),
        "post_trade_hs": {},
        "post_trade_products": {},
        "output_root": Path("outputs"),
        "reference_quantity": 10.0,
        "theme": "dark",
        "sort_mode": "size",
        "image_width": 2200,
        "image_scale": 1.0,
        "label_font_size": 12,
    }
    values.update(overrides)
    return Settings(**values)


def reference(*country_ids: int) -> ReferenceMaps:
    return ReferenceMaps(
        names={country_id: f"Country {country_id}" for country_id in country_ids},
        iso3={country_id: f"C{country_id}" for country_id in country_ids},
        colors={country_id: "#336699" for country_id in country_ids},
        regions={country_id: "Asia" for country_id in country_ids},
    )


class RouteTests(unittest.TestCase):
    def test_manganese_is_supported(self) -> None:
        self.assertEqual(normalize_metal("manganese"), "Mn")

    def test_iso3_mode_changes_visible_label_but_preserves_full_hover(self) -> None:
        graph = GraphBuilder(reference(100), {}, "iso3")
        key = graph.ensure_country("P:mining", 100)
        self.assertEqual(graph.nodes[key].label, "C100")
        self.assertEqual(graph.nodes[key].hover, "Country 100 (C100)")

    def test_dynamic_default_route_has_six_production_stages(self) -> None:
        route = route_from_options(False, True, True)
        self.assertEqual(
            [stage.key for stage in route.production_stages],
            ["mining", "processing", "refining", "pcam", "cathode", "battery"],
        )
        self.assertEqual(len(display_stages(route)), 11)

    def test_dynamic_route_merges_processing_and_can_bypass_pcam(self) -> None:
        route = route_from_options(True, False, True)
        self.assertEqual(
            [stage.key for stage in route.production_stages],
            ["mining", "pro_ref", "cathode", "battery"],
        )
    def test_routes_create_five_seven_and_nine_display_stages(self) -> None:
        self.assertEqual(len(display_stages(ROUTES["intermediate"])), 5)
        self.assertEqual(len(display_stages(ROUTES["full"])), 7)
        self.assertEqual(len(display_stages(ROUTES["completed"])), 9)

    def test_legacy_route_names_resolve_to_canonical_names(self) -> None:
        self.assertEqual(route_for("pro_ref").key, "intermediate")
        self.assertEqual(route_for("pcam").key, "completed")


class TradeLoaderTests(unittest.TestCase):
    def test_import_reporter_and_export_partner_direction_and_world_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reporter = root / "UNComtrade_2024_Import_ByPartner" / "reporter_100"
            reporter.mkdir(parents=True)
            path = reporter / "100_260400_M_2024_partners.csv"
            path.write_text(
                "partnerCode,qtyUnitAbbr,qty,netWgt\n"
                "0,kg,9000,9000\n"
                "200,kg,2500,2500\n",
                encoding="utf-8",
            )
            records = load_trade_records(
                settings(
                    trade_root=root,
                    post_trade_hs={"post_trade_1": {"260400": 0.5}},
                ),
                "post_trade_1",
            )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].importer_id, 100)
        self.assertEqual(records[0].exporter_id, 200)
        self.assertAlmostEqual(records[0].raw_quantity_tonnes, 2.5)

    def test_net_weight_alias_is_used_when_qty_unit_is_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reporter = root / "UNComtrade_2019_Import_ByPartner" / "reporter_100"
            reporter.mkdir(parents=True)
            path = reporter / "100_260400_M_2019_partners.csv"
            path.write_text(
                "partnerCode,qtyUnitAbbr,qty,netWeight\n"
                "200,N/A,,2500\n",
                encoding="utf-8",
            )
            records = load_trade_records(
                settings(
                    year=2019,
                    trade_root=root,
                    post_trade_hs={"post_trade_1": {"260400": 0.5}},
                ),
                "post_trade_1",
            )
        self.assertEqual(len(records), 1)
        self.assertAlmostEqual(records[0].raw_quantity_tonnes, 2.5)

    def test_net_weight_fallback_is_applied_per_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reporter = root / "UNComtrade_2024_Import_ByPartner" / "reporter_100"
            reporter.mkdir(parents=True)
            path = reporter / "100_260400_M_2024_partners.csv"
            path.write_text(
                "partnerCode,qtyUnitAbbr,qty,netWgt\n"
                "200,kg,2500,2500\n"
                "300,N/A,,4000\n",
                encoding="utf-8",
            )
            records = load_trade_records(
                settings(
                    trade_root=root,
                    post_trade_hs={"post_trade_1": {"260400": 0.5}},
                ),
                "post_trade_1",
            )
        quantities = {record.exporter_id: record.raw_quantity_tonnes for record in records}
        self.assertEqual(quantities, {200: 2.5, 300: 4.0})

    def test_empty_quantity_values_contribute_zero_without_stopping_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reporter = root / "UNComtrade_2018_Import_ByPartner" / "reporter_100"
            reporter.mkdir(parents=True)
            path = reporter / "100_260400_M_2018_partners.csv"
            path.write_text(
                "partnerCode,qtyUnitAbbr,qty,netWeight\n"
                "200,N/A,,\n",
                encoding="utf-8",
            )
            records = load_trade_records(
                settings(
                    year=2018,
                    trade_root=root,
                    post_trade_hs={"post_trade_1": {"260400": 0.5}},
                ),
                "post_trade_1",
            )
        self.assertEqual(records, [])


class ScalingTests(unittest.TestCase):
    def test_chemistry_weighted_factor_matches_production_shares(self) -> None:
        production = ProductionData(
            totals={"cathode": {1: 100.0}, "battery": {2: 100.0}},
            labels={1: "A", 2: "B"}, cathode_chemistry={"LFP": {1: 50.0}, "NCA": {1: 50.0}},
            stage_chemistry={"cathode": {"LFP": {1: 50.0}, "NCA": {1: 50.0}}},
        )
        record = TradeRecord("post_trade_5", "X", 2, 1, 100.0, 1.0)
        _apply_chemistry_weighted_factors(
            [record], "cathode", "battery",
            settings(chemistry_conversion_factors={"LFP": 0.2, "NCA": 0.4}), production,
        )
        self.assertAlmostEqual(record.manual_conversion_factor, 0.3)

    def test_only_producer_exporters_receive_production_scaling(self) -> None:
        producer = TradeRecord("post_trade_1", "260400", 2, 1, 20.0, 0.5)
        non_source = TradeRecord("post_trade_1", "260400", 2, 3, 4.0, 0.5)
        ignored_nn = TradeRecord("post_trade_1", "260400", 4, 3, 6.0, 0.5)
        records = [producer, non_source, ignored_nn]
        _prepare_trade_records(records, {1: 5.0}, {2: 7.0})

        self.assertAlmostEqual(producer.production_scaling_multiplier, 0.5)
        self.assertAlmostEqual(producer.effective_conversion_factor, 0.25)
        self.assertAlmostEqual(producer.final_trade_quantity_tonnes, 5.0)
        self.assertAlmostEqual(non_source.production_scaling_multiplier, 1.0)
        self.assertAlmostEqual(non_source.effective_conversion_factor, 0.5)
        self.assertAlmostEqual(non_source.exporter_total_before_scaling, 5.0)
        self.assertTrue(non_source.included_in_sankey)
        self.assertFalse(ignored_nn.included_in_sankey)


class BalanceTests(unittest.TestCase):
    def test_unmerged_lmfp_becomes_other_at_battery(self) -> None:
        production = ProductionData(
            totals={"battery": {1: 100.0}}, labels={1: "A"}, cathode_chemistry={},
            stage_chemistry={"battery": {"LFP": {1: 60.0}, "NMC": {1: 40.0}}},
        )
        values = _chemistry_values(
            production, 1, 100.0,
            {"LFP": 30.0, "LMFP": 20.0, "NMC": 50.0}, stage_name="battery",
        )
        self.assertAlmostEqual(values["OTHER"], 20.0)
        self.assertAlmostEqual(sum(values.values()), 100.0)

    def test_lithium_feedstock_affinity_routes_to_battery_chemistry(self) -> None:
        production = ProductionData(
            totals={"cathode": {1: 100.0}},
            labels={1: "A"},
            cathode_chemistry={"LFP": {1: 60.0}, "NMC": {1: 40.0}},
        )
        carbonate = _chemistry_values(
            production, 1, 100.0, {"Lithium Carbonate": 10.0}
        )
        hydroxide = _chemistry_values(
            production, 1, 100.0, {"Lithium Hydroxide": 10.0}
        )
        self.assertGreater(carbonate["LFP"], carbonate["NMC"])
        self.assertGreater(hydroxide["NMC"], hydroxide["LFP"])
        self.assertAlmostEqual(sum(carbonate.values()), 100.0)
        self.assertAlmostEqual(sum(hydroxide.values()), 100.0)

    def test_empty_trade_step_continues_domestic_and_unknown_balance(self) -> None:
        route = RouteSpec(
            key="test",
            production_stages=(ProductionStage("mining", "Mining"), ProductionStage("cathode", "Cathode")),
            transitions=(TransitionSpec("post_trade_1", "1st Post Trade", "mining", "cathode"),),
        )
        production = ProductionData(
            totals={"mining": {1: 10.0}, "cathode": {1: 7.0}},
            labels={1: "Country 1"},
            cathode_chemistry={},
        )
        result = build_flow_graph(
            settings(route="test"),
            route,
            production,
            reference(1),
            {"post_trade_1": []},
        )
        row = result.balance_rows[0]
        self.assertEqual(row["trade_exports"], 0.0)
        self.assertEqual(row["trade_imports"], 0.0)
        self.assertEqual(row["domestic_flow"], 10.0)
        self.assertEqual(row["excess_to_unknown_destination"], 3.0)
        self.assertAlmostEqual(row["source_balance_residual"], 0.0)
        self.assertAlmostEqual(row["post_trade_balance_residual"], 0.0)

    def test_country_chemistry_creates_country_product_nodes(self) -> None:
        route = RouteSpec(
            key="test",
            production_stages=(ProductionStage("mining", "Mining"), ProductionStage("cathode", "Cathode")),
            transitions=(TransitionSpec("post_trade_1", "1st Post Trade", "mining", "cathode"),),
        )
        production = ProductionData(
            totals={"mining": {1: 5.0}, "cathode": {1: 5.0}},
            labels={1: "Country 1"},
            cathode_chemistry={"NMC": {1: 3.0}, "NCA": {1: 2.0}},
        )
        result = build_flow_graph(
            settings(route="test", cathode_view="country_chemistry"),
            route,
            production,
            reference(1),
            {"post_trade_1": []},
        )
        labels = {node.label for node in result.nodes.values()}
        self.assertIn("Country 1 / NMC", labels)
        self.assertIn("Country 1 / NCA", labels)

    def test_chemistry_only_creates_global_product_nodes(self) -> None:
        route = RouteSpec(
            key="test",
            production_stages=(ProductionStage("mining", "Mining"), ProductionStage("cathode", "Cathode")),
            transitions=(TransitionSpec("post_trade_1", "1st Post Trade", "mining", "cathode"),),
        )
        production = ProductionData(
            totals={"mining": {1: 5.0}, "cathode": {1: 5.0}},
            labels={1: "Country 1"},
            cathode_chemistry={"NMC": {1: 3.0}, "NCA": {1: 2.0}},
        )
        result = build_flow_graph(
            settings(route="test", cathode_view="chemistry_only"),
            route,
            production,
            reference(1),
            {"post_trade_1": []},
        )
        cathode_nodes = [node for node in result.nodes.values() if node.stage == "P:cathode"]
        self.assertEqual({node.label for node in cathode_nodes}, {"NMC", "NCA", "Mining to Unknown Destination"})


class TradeOnlyBalanceTests(unittest.TestCase):
    def test_trade_only_chemistry_uses_production_shares_not_production_total(self) -> None:
        production = ProductionData(
            totals={"cathode": {1: 5.0}},
            labels={1: "Country 1"},
            cathode_chemistry={"NMC": {1: 3.0}, "NCA": {1: 2.0}},
        )
        values = _chemistry_values(production, 1, 20.0)
        self.assertAlmostEqual(values["NMC"], 12.0)
        self.assertAlmostEqual(values["NCA"], 8.0)

    def test_downstream_deficit_propagates_back_to_mining(self) -> None:
        route = RouteSpec(
            key="test_full",
            production_stages=(
                ProductionStage("mining", "Mining"),
                ProductionStage("processing", "Processing"),
                ProductionStage("refining", "Refining"),
                ProductionStage("cathode", "Cathode"),
            ),
            transitions=(
                TransitionSpec("post_trade_1", "1st Post Trade", "mining", "processing"),
                TransitionSpec("post_trade_2", "2nd Post Trade", "processing", "refining"),
                TransitionSpec("post_trade_3", "3rd Post Trade", "refining", "cathode"),
            ),
        )
        production = ProductionData(
            totals={stage.key: {1: 1.0} for stage in route.production_stages},
            labels={1: "Country 1"},
            cathode_chemistry={},
        )
        trades = {
            "post_trade_1": [TradeRecord("post_trade_1", "A", 1, 1, 5.0, 1.0)],
            "post_trade_2": [TradeRecord("post_trade_2", "B", 1, 1, 3.0, 1.0)],
            "post_trade_3": [TradeRecord("post_trade_3", "C", 1, 1, 10.0, 1.0)],
        }
        result = build_flow_graph(
            settings(route="test_full", use_production_data=False),
            route,
            production,
            reference(1),
            trades,
        )
        rows = {row["production_stage"]: row for row in result.stage_rows}
        self.assertAlmostEqual(rows["mining"]["domestic_to_downstream"], 5.0)
        self.assertAlmostEqual(rows["processing"]["domestic_to_downstream"], 7.0)
        self.assertAlmostEqual(rows["refining"]["domestic_to_downstream"], 0.0)
        self.assertEqual({row["node_size"] for row in result.stage_rows}, {10.0})
        self.assertTrue(all(abs(row["material_balance_residual"]) < 1e-9 for row in result.stage_rows))
        self.assertTrue(
            all(record.production_scaling_multiplier == 1.0 for records in trades.values() for record in records)
        )

    def test_membership_gap_turns_surplus_into_unknown_destination(self) -> None:
        route = RouteSpec(
            key="test_gap",
            production_stages=(
                ProductionStage("mining", "Mining"),
                ProductionStage("processing", "Processing"),
                ProductionStage("cathode", "Cathode"),
            ),
            transitions=(
                TransitionSpec("post_trade_1", "1st Post Trade", "mining", "processing"),
                TransitionSpec("post_trade_2", "2nd Post Trade", "processing", "cathode"),
            ),
        )
        production = ProductionData(
            totals={"mining": {2: 1.0}, "processing": {1: 1.0, 3: 1.0}, "cathode": {2: 1.0}},
            labels={1: "Country 1", 2: "Country 2", 3: "Country 3"},
            cathode_chemistry={},
        )
        trades = {
            "post_trade_1": [
                TradeRecord("post_trade_1", "A", 1, 2, 6.0, 1.0),
                TradeRecord("post_trade_1", "A", 3, 2, 4.0, 1.0),
            ],
            "post_trade_2": [
                TradeRecord("post_trade_2", "B", 2, 1, 4.0, 1.0),
                TradeRecord("post_trade_2", "B", 2, 3, 6.0, 1.0),
            ],
        }
        result = build_flow_graph(
            settings(route="test_gap", use_production_data=False),
            route,
            production,
            reference(1, 2, 3),
            trades,
        )
        processing = next(
            row for row in result.stage_rows
            if row["production_stage"] == "processing" and row["country_id"] == 1
        )
        self.assertAlmostEqual(processing["unknown_destination"], 2.0)
        self.assertEqual(processing["domestic_from_upstream"], 0.0)
        self.assertEqual(processing["domestic_to_downstream"], 0.0)
        processing_deficit = next(
            row for row in result.stage_rows
            if row["production_stage"] == "processing" and row["country_id"] == 3
        )
        self.assertAlmostEqual(processing_deficit["unknown_source"], 2.0)
        self.assertEqual(processing_deficit["unknown_destination"], 0.0)


class ProductionTests(unittest.TestCase):
    def test_mixed_source_filename_tag_records_each_active_stage(self) -> None:
        route = RouteSpec(
            "two",
            (ProductionStage("mining", "Mining"), ProductionStage("cathode", "Cathode")),
            (),
        )
        tag = _production_source_tag(
            settings(
                production_source="mixed",
                production_sources_by_stage={"mining": "usgs", "cathode": "benchmark"},
            ),
            route,
        )
        self.assertEqual(tag, "mining-usgs_cathode-benchmark")

    def test_consolidated_workbooks_can_be_selected_per_stage(self) -> None:
        route = RouteSpec(
            "two",
            (ProductionStage("mining", "Mining"), ProductionStage("cathode", "Cathode")),
            (),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mining_book = root / "usgs.xlsx"
            cathode_book = root / "scinsight.xlsx"
            pd.DataFrame(
                {
                    "id": [1],
                    "reporterDesc": ["Mining A"],
                    "product": ["Total"],
                    "status": ["all"],
                    2024: [10.0],
                }
            ).to_excel(mining_book, sheet_name="nickel_mining", index=False)
            pd.DataFrame(
                {
                    "id": [2, 2],
                    "reporterDesc": ["Cathode B", "Cathode B"],
                    "product": ["Total", "NMC"],
                    "status": ["operating", "operating"],
                    2024: [20.0, 20.0],
                }
            ).to_excel(cathode_book, sheet_name="nickel_cathode", index=False)

            production = load_production(
                settings(
                    production_source="mixed",
                    production_sheets=("operating",),
                    production_sources_by_stage={"mining": "usgs", "cathode": "scinsight"},
                    production_roots={"usgs": mining_book, "scinsight": cathode_book},
                    production_all_status_sources=frozenset({"usgs"}),
                ),
                route,
            )

            self.assertEqual(production.totals["mining"], {1: 10.0})
            self.assertEqual(production.totals["cathode"], {2: 20.0})
            self.assertEqual(
                [(row["stage"], row["production_source"], row["sheet"]) for row in production.sheet_summary_rows],
                [("mining", "usgs", "all"), ("cathode", "scinsight", "operating")],
            )

    def test_missing_consolidated_stage_sheet_reports_source_and_stage(self) -> None:
        route = RouteSpec("one", (ProductionStage("processing", "Processing"),), ())
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook = Path(temp_dir) / "usgs.xlsx"
            pd.DataFrame(
                {"id": [1], "reporterDesc": ["A"], "product": ["Total"], "status": ["all"], 2024: [1]}
            ).to_excel(workbook, sheet_name="nickel_mining", index=False)
            with self.assertRaisesRegex(
                FileNotFoundError,
                "source=usgs.*stage=processing.*expected_sheet=nickel_processing",
            ):
                load_production(
                    settings(
                        production_source="usgs",
                        production_sources_by_stage={"processing": "usgs"},
                        production_roots={"usgs": workbook},
                        production_all_status_sources=frozenset({"usgs"}),
                    ),
                    route,
                )

    def test_selected_production_sheets_are_summed(self) -> None:
        route = RouteSpec("one", (ProductionStage("mining", "Mining"),), ())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nickel_mining.xlsx"
            with pd.ExcelWriter(path) as writer:
                pd.DataFrame({"id": [1], "reporterDesc": ["A"], "product": ["Total"], 2024: [10]}).to_excel(
                    writer, sheet_name="operating", index=False
                )
                pd.DataFrame({"id": [1], "reporterDesc": ["A"], "product": ["Total"], 2024: [5]}).to_excel(
                    writer, sheet_name="highly probable", index=False
                )
                pd.DataFrame({"id": [1], "reporterDesc": ["A"], "product": ["Total"], 2024: [99]}).to_excel(
                    writer, sheet_name="possible", index=False
                )
            production = load_production(
                settings(
                    production_root=Path(temp_dir),
                    production_source="scinsight",
                    production_sheets=("operating", "highly probable"),
                ),
                route,
            )
            self.assertEqual(production.totals["mining"][1], 15.0)
            self.assertEqual([row["sheet"] for row in production.sheet_summary_rows], ["operating", "highly probable"])

    def test_missing_selected_sheet_reports_available_sheets(self) -> None:
        route = RouteSpec("one", (ProductionStage("mining", "Mining"),), ())
        with tempfile.TemporaryDirectory() as temp_dir:
            pd.DataFrame({"id": [1], "Desc": ["A"], 2024: [10]}).to_excel(
                Path(temp_dir) / "nickel_mining.xlsx", sheet_name="operating", index=False
            )
            with self.assertRaisesRegex(ValueError, "requested=.*highly probable.*available=.*operating"):
                load_production(
                    settings(
                        production_root=Path(temp_dir),
                        production_source="scinsight",
                        production_sheets=("highly probable",),
                    ),
                    route,
                )

    def test_missing_route_stage_file_reports_the_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pd.DataFrame({"id": [1], "Desc": ["Country 1"], "2024": [10.0]}).to_excel(
                Path(temp_dir) / "nickel_mining.xlsx",
                index=False,
            )
            with self.assertRaisesRegex(FileNotFoundError, "stage=pro_ref"):
                load_production(
                    settings(production_root=Path(temp_dir), route="intermediate"),
                    ROUTES["intermediate"],
                )


class RendererTests(unittest.TestCase):
    def test_transparency_filters_preserve_special_nodes_and_selected_countries(self) -> None:
        stages = display_stages(ROUTES["intermediate"])
        source_stage = stages[0].key
        target_stage = stages[-1].key
        nodes = {
            "P:mining:country:1": NodeSpec("P:mining:country:1", source_stage, "Country 1", "#111111", "regular", "Country 1", "Asia"),
            "P:cathode:country:2": NodeSpec("P:cathode:country:2", target_stage, "Country 2", "#222222", "regular", "Country 2", "Asia"),
            "P:cathode:country:3": NodeSpec("P:cathode:country:3", target_stage, "Country 3", "#333333", "regular", "Country 3", "Asia"),
            "P:mining:special:unknown": NodeSpec("P:mining:special:unknown", source_stage, "Unknown source", "#8b929a", "source_special", "Unknown source", "Unknown"),
        }
        figure = make_figure(
            nodes=nodes,
            links=[
                LinkSpec("P:mining:country:1", "P:cathode:country:2", 5.0, "rgba(17,17,17,0.34)"),
                LinkSpec("P:mining:special:unknown", "P:cathode:country:3", 1.0, "rgba(139,146,154,0.34)"),
            ],
            stages=stages,
            metal="Ni",
            route="intermediate",
            reference_quantity=10.0,
            theme="light",
            sort_mode="size",
            label_font_size=16,
            flow_transparency_threshold=10.0,
            node_transparency_threshold=10.0,
            preserved_country_ids=frozenset({1}),
        )
        trace = figure.data[0]
        node_rows = {
            str(customdata).split("<br>", 1)[0]: (label, color)
            for customdata, label, color in zip(trace.node.customdata, trace.node.label, trace.node.color)
        }
        self.assertEqual(node_rows["Country 1"], ("Country 1", "#111111"))
        self.assertEqual(node_rows["Country 2"], ("", "rgba(0,0,0,0)"))
        self.assertEqual(node_rows["Unknown source"], ("Unknown source", "#8b929a"))
        self.assertEqual(list(trace.link.color).count("rgba(0,0,0,0)"), 1)

    def test_renderer_uses_dynamic_stage_count(self) -> None:
        stages = display_stages(ROUTES["intermediate"])
        nodes = {
            stages[0].key: NodeSpec(stages[0].key, stages[0].key, "A", "#336699", "regular", "A", "Asia"),
            stages[-1].key: NodeSpec(stages[-1].key, stages[-1].key, "B", "#663399", "regular", "B", "Asia"),
        }
        links = [LinkSpec(stages[0].key, stages[-1].key, 5.0, "rgba(51,102,153,0.34)")]
        figure = make_figure(
            nodes=nodes,
            links=links,
            stages=stages,
            metal="Ni",
            route="intermediate",
            reference_quantity=10.0,
            theme="dark",
            sort_mode="size",
            label_font_size=16,
        )
        stage_annotations = [annotation for annotation in figure.layout.annotations if "Reference Node" not in annotation.text]
        reference_annotations = [annotation for annotation in figure.layout.annotations if "Reference Node" in annotation.text]
        self.assertEqual(len(stage_annotations), 5)
        self.assertEqual(figure.layout.font.size, 16)
        self.assertTrue(all(annotation.font.size == 16 for annotation in stage_annotations))
        self.assertEqual(len(reference_annotations), 1)
        self.assertEqual(reference_annotations[0].font.size, 16)
        self.assertEqual(figure.layout.paper_bgcolor, "#FFFFFF")


if __name__ == "__main__":
    unittest.main()
