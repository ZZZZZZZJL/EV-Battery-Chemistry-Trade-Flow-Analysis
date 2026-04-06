from __future__ import annotations

import re
import unittest

from battery_7step_site.api.routes import FigureRequestModel, bootstrap, figure
from battery_7step_site.main import healthz
from battery_7step_site.services.cobalt_data import load_year_inputs as load_cobalt_year_inputs
from battery_7step_site.services.cobalt_sankey import _build_country_payload as build_cobalt_country_payload
from battery_7step_site.services.precomputed_repository import get_repository
from battery_7step_site.services.precomputed_site import build_app_payload, build_figure
from battery_7step_site.services.runtime_checks import gather_runtime_status
from trade_flow_opt import pipeline_v1


class WebViewerTests(unittest.TestCase):
    def test_repository_detects_expected_metals_and_years(self) -> None:
        repo = get_repository()
        self.assertEqual(repo.metals, ["Ni", "Li", "Co"])
        self.assertEqual(repo.years, [2020, 2021, 2022, 2023, 2024])

    def test_build_figure_from_precomputed_files(self) -> None:
        repo = get_repository()
        figure_payload, _, _, _, _ = build_figure(
            repo,
            "Li",
            2024,
            "optimized_v3",
            "light",
            1_000_000,
            {},
            {},
            {},
        )
        self.assertIn("data", figure_payload)
        self.assertEqual(figure_payload["data"][0]["type"], "sankey")
        self.assertGreater(len(figure_payload["data"][0]["node"]["label"]), 0)
        self.assertGreater(len(figure_payload["data"][0]["link"]["value"]), 0)

    def test_guest_mode_redacts_hover_numbers(self) -> None:
        repo = get_repository()
        figure_payload, _, _, _, _ = build_figure(
            repo,
            "Ni",
            2024,
            "baseline",
            "light",
            1_000_000,
            {},
            {},
            {},
            access_mode="guest",
        )
        trace = figure_payload["data"][0]
        quantity_pattern = re.compile(r"[0-9,]+(?:\.[0-9]+)? t")
        self.assertTrue(all(not quantity_pattern.search(str(value)) for value in trace["node"]["customdata"]))
        self.assertTrue(all(not quantity_pattern.search(str(value)) for value in trace["link"]["customdata"]))
        self.assertTrue(all("Source:" in str(value) and "Target:" in str(value) for value in trace["link"]["customdata"]))
        self.assertEqual(trace["link"]["hovertemplate"], "%{customdata}<extra></extra>")

    def test_continent_sort_aggregates_stage_nodes(self) -> None:
        repo = get_repository()
        baseline_figure, _, _, _, _ = build_figure(
            repo,
            "Ni",
            2024,
            "baseline",
            "light",
            1_000_000,
            {},
            {},
            {},
        )
        continent_figure, _, _, _, _ = build_figure(
            repo,
            "Ni",
            2024,
            "baseline",
            "light",
            1_000_000,
            {"S5": "continent"},
            {},
            {},
        )
        baseline_labels = baseline_figure["data"][0]["node"]["label"]
        continent_labels = continent_figure["data"][0]["node"]["label"]
        self.assertGreater(len(baseline_labels), len(continent_labels))
        self.assertTrue(any(label in {"Africa", "Asia", "Europe", "North America", "South America", "Oceania"} for label in continent_labels))

    def test_aggregate_tail_count_collapses_tail_nodes(self) -> None:
        repo = get_repository()
        baseline_figure, stage_controls, _, _, aggregate_counts = build_figure(
            repo,
            "Ni",
            2024,
            "baseline",
            "light",
            1_000_000,
            {},
            {},
            {},
        )
        aggregated_figure, aggregated_stage_controls, _, _, aggregated_counts = build_figure(
            repo,
            "Ni",
            2024,
            "baseline",
            "light",
            1_000_000,
            {},
            {},
            {},
            {"S5": 2},
        )
        self.assertEqual(aggregate_counts["S5"], 0)
        self.assertEqual(aggregated_counts["S5"], 2)
        self.assertGreater(stage_controls["S5"]["maxAggregateCount"], 0)
        self.assertEqual(aggregated_stage_controls["S5"]["aggregateCount"], 2)
        self.assertLess(len(aggregated_figure["data"][0]["node"]["label"]), len(baseline_figure["data"][0]["node"]["label"]))
        self.assertIn("Other 2 Countries", aggregated_figure["data"][0]["node"]["label"])

    def test_compare_payload_contains_metrics_and_parameters_for_co_max(self) -> None:
        repo = get_repository()
        payload = build_app_payload(
            repo,
            "Co",
            2024,
            "optimized_v3",
            "compare",
            cobalt_mode="max",
            access_mode="analyst",
        )
        self.assertEqual(payload["cobaltMode"], "max")
        self.assertGreater(len(payload["tables"]["metrics"]), 0)
        self.assertGreater(len(payload["tables"]["parameters"]), 0)
        self.assertGreater(len(payload["tables"]["transitions"]), 0)
        self.assertGreater(len(payload["tables"]["producerCoefficients"]), 0)

    def test_v3_parameter_rows_only_include_active_v3_params(self) -> None:
        repo = get_repository()
        rows = repo.build_parameter_rows("Li", "optimized_v3", "compare")
        parameters = [row["parameter"] for row in rows]
        self.assertIn("PP Deviation Penalty", parameters)
        self.assertNotIn("Mirror Weight", parameters)

    def test_v3_payload_contains_stage_level_producer_coefficients(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Li", 2024, "optimized_v3", "compare", access_mode="analyst")
        rows = payload["tables"]["producerCoefficients"]
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["transition_display"], "S1-S3: 1st Post Trade")
        self.assertIn("hs_code", rows[0])
        self.assertIn("producer_scope", rows[0])
        self.assertIn("coef_value", rows[0])
        self.assertNotIn("156", rows[0]["producer_scope"])

    def test_guest_mode_hides_diagnostics(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Ni", 2024, "baseline", "compare", access_mode="guest")
        self.assertEqual(payload["accessMode"], "guest")
        self.assertEqual(payload["tables"]["metrics"], [])
        self.assertEqual(payload["tables"]["transitions"], [])
        self.assertEqual(payload["stageSummary"], [])

    def test_placeholder_hs_folders_are_omitted_from_diagnostics(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Li", 2024, "optimized_v3", "compare", access_mode="analyst")
        folder_names = [row["folder_name"] for row in payload["tables"]["transitions"]]
        self.assertNotIn("2nd_post_trade/Li_000000", folder_names)

    def test_reference_quantity_changes_figure_height(self) -> None:
        repo = get_repository()
        figure_default, _, _, _, _ = build_figure(repo, "Ni", 2024, "baseline", "light", 1_000_000, {}, {}, {})
        figure_small_ref, _, _, _, _ = build_figure(repo, "Ni", 2024, "baseline", "light", 300_000, {}, {}, {})
        self.assertGreater(figure_small_ref["layout"]["height"], figure_default["layout"]["height"])

    def test_zero_value_special_nodes_are_pruned_from_precomputed_figure(self) -> None:
        repo = get_repository()
        figure_payload, stage_controls, _, _, _ = build_figure(repo, "Li", 2024, "baseline", "light", 1_000_000, {}, {}, {})
        labels = set(figure_payload["data"][0]["node"]["label"])
        self.assertNotIn("Processing to Non-Refining Countries", labels)
        self.assertNotIn("From Non-Processing Countries", labels)
        self.assertNotIn("Processing to Unknown Destination", labels)
        s3_items = {item["label"] for item in stage_controls["S3"]["items"]}
        self.assertNotIn("From Non-Processing Countries", s3_items)

    def test_bootstrap_exposes_defaults_and_cobalt_modes(self) -> None:
        payload = bootstrap()
        metadata = payload["metadata"]
        self.assertEqual(metadata["defaultMetal"], "Ni")
        self.assertEqual(metadata["defaultTheme"], "light")
        self.assertEqual(metadata["defaultYear"], 2024)
        self.assertEqual(metadata["defaultReferenceQuantity"], 1_000_000.0)
        self.assertEqual(
            metadata["defaultReferenceQuantities"],
            {"Ni": 1_000_000.0, "Li": 50_000.0, "Co": 50_000.0},
        )
        self.assertEqual(metadata["defaultAccessMode"], "guest")
        self.assertEqual(metadata["cobaltModes"], ["mid", "max", "min"])
        self.assertEqual(metadata["resultLabels"]["optimized_v3"], "First Optimization")
        self.assertEqual(metadata["resultLabels"]["optimized_v4"], "Second Optimization")

    def test_build_app_payload_uses_per_metal_default_reference_quantity(self) -> None:
        repo = get_repository()
        li_payload = build_app_payload(repo, "Li", 2024, "baseline", "compare", reference_qty=None, access_mode="guest")
        co_payload = build_app_payload(repo, "Co", 2024, "baseline", "compare", reference_qty=None, access_mode="guest")
        ni_payload = build_app_payload(repo, "Ni", 2024, "baseline", "compare", reference_qty=None, access_mode="guest")
        self.assertEqual(li_payload["referenceQuantity"], 50_000.0)
        self.assertEqual(co_payload["referenceQuantity"], 50_000.0)
        self.assertEqual(ni_payload["referenceQuantity"], 1_000_000.0)

    def test_dataset_status_uses_labels_not_server_paths(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Ni", 2024, "baseline", "compare", access_mode="guest")
        dataset_status = payload["datasetStatus"]
        self.assertIn("label", dataset_status["Original Export"])
        self.assertNotIn("path", dataset_status["Original Export"])

    def test_runtime_status_and_healthz_report_ready(self) -> None:
        status = gather_runtime_status()
        self.assertTrue(status.ready)
        self.assertGreater(len(status.checks), 0)
        response = healthz()
        self.assertEqual(response.status_code, 200)
        payload = response.body.decode("utf-8")
        self.assertIn('"ready":true', payload)
        self.assertIn('"checks"', payload)

    def test_route_helpers_return_bootstrap_and_figure(self) -> None:
        response = figure(
            FigureRequestModel(
                metal="Co",
                year=2024,
                theme="light",
                resultMode="optimized_v4",
                tableView="compare",
                referenceQuantity=1_000_000,
                sortModes={},
                stageOrders={},
                specialPositions={},
                aggregateCounts={},
                cobaltMode="min",
                accessMode="analyst",
                accessPassword="88888888",
            )
        )
        self.assertEqual(response.status_code, 200)
        payload = response.body.decode("utf-8")
        self.assertIn('"resultMode":"optimized_v4"', payload)
        self.assertIn('"cobaltMode":"min"', payload)
        self.assertIn('"accessMode":"analyst"', payload)
        self.assertIn('"figure"', payload)

    def test_cobalt_second_post_trade_china_balances_in_country_payload(self) -> None:
        nodes, links = build_cobalt_country_payload(load_cobalt_year_inputs(2024), "mid")
        del nodes
        s4_china_key = "S4:country:156"
        incoming = sum(link.value for link in links if link.target == s4_china_key)
        outgoing = sum(link.value for link in links if link.source == s4_china_key)
        self.assertAlmostEqual(incoming, outgoing, places=6)

    def test_pipeline_prefers_local_battery_7step_site_modules(self) -> None:
        cobalt_module = pipeline_v1._bundle("Co")["sankey"]
        self.assertIn("trade_flow_opt", str(cobalt_module.__file__))


if __name__ == "__main__":
    unittest.main()
