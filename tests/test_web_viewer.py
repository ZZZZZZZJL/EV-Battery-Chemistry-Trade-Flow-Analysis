from __future__ import annotations

from pathlib import Path
import re
import unittest

from battery_7step_site.api.routes import FigureRequestModel, bootstrap, figure
from battery_7step_site.main import healthz
from battery_7step_site.services.precomputed_repository import get_repository
from battery_7step_site.services.precomputed_site import (
    build_app_payload,
    build_figure,
    clear_default_payload_cache,
    default_payload_cache_info,
)
from battery_7step_site.services.runtime_checks import gather_runtime_status
from trade_flow.baseline import pipeline_v1
from trade_flow.publishing.refresh_precomputed_from_inputs import build_case_graphs_from_inputs_json


class WebViewerTests(unittest.TestCase):
    def _country_stage_deltas(self, links, stage: str) -> dict[str, float]:
        keys = sorted(
            {
                link.source
                for link in links
                if link.source.startswith(f"{stage}:country:")
            }
            | {
                link.target
                for link in links
                if link.target.startswith(f"{stage}:country:")
            }
        )
        return {
            key: (
                sum(link.value for link in links if link.target == key)
                - sum(link.value for link in links if link.source == key)
            )
            for key in keys
        }

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
            "first_optimization",
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
        self.assertEqual(
            len(figure_payload["data"][0]["ids"]),
            len(figure_payload["data"][0]["node"]["label"]),
        )
        self.assertTrue(all(str(node_id).startswith("S") for node_id in figure_payload["data"][0]["ids"]))

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
            "first_optimization",
            "compare",
            cobalt_mode="max",
            access_mode="analyst",
        )
        self.assertEqual(payload["cobaltMode"], "max")
        self.assertGreater(len(payload["tables"]["metrics"]), 0)
        self.assertGreater(len(payload["tables"]["parameters"]), 0)
        self.assertGreater(len(payload["tables"]["transitions"]), 0)
        self.assertGreater(len(payload["tables"]["producerCoefficients"]), 0)

    def test_first_optimization_parameter_rows_read_conversion_factor_optimization_notes(self) -> None:
        repo = get_repository()
        rows = repo.build_parameter_rows("Li", "first_optimization", "compare", year=2024)
        parameter_names = [row["Parameter"] for row in rows]
        self.assertIn("Data Source", parameter_names)
        self.assertIn("alpha", parameter_names)
        self.assertIn("beta_pp", parameter_names)
        self.assertIn("Bounds", parameter_names)
        self.assertIn("Source Scaling", parameter_names)
        data_source_row = next(row for row in rows if row["Parameter"] == "Data Source")
        self.assertEqual(data_source_row["Value"], "conversion_factor_optimization")

    def test_first_optimization_metric_rows_include_bound_hits_and_special_total(self) -> None:
        repo = get_repository()
        rows = repo.build_metric_rows("Ni", 2024, "first_optimization", "compare")
        metric_names = [row["Metric"] for row in rows]
        self.assertIn("Bound Hits", metric_names)
        self.assertIn("Representative Special Total", metric_names)

    def test_first_optimization_payload_contains_conversion_factor_rows(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Li", 2024, "first_optimization", "compare", access_mode="analyst")
        rows = payload["tables"]["producerCoefficients"]
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["transition_display"], "S1-S2-S3")
        self.assertIn("hs_code", rows[0])
        self.assertIn("producer_scope", rows[0])
        self.assertIn("coef_value", rows[0])
        self.assertIn(rows[0]["coefficient_class"], {"A", "B", "G", "NN"})

    def test_guest_mode_hides_diagnostics(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Ni", 2024, "baseline", "compare", access_mode="guest")
        self.assertEqual(payload["accessMode"], "guest")
        self.assertEqual(payload["tables"]["metrics"], [])
        self.assertEqual(payload["tables"]["transitions"], [])
        self.assertEqual(payload["stageSummary"], [])

    def test_unsupported_li_trade2_case_is_kept_as_stage_level_diagnostic(self) -> None:
        repo = get_repository()
        payload = build_app_payload(repo, "Li", 2024, "first_optimization", "compare", access_mode="analyst")
        rows = payload["tables"]["transitions"]
        li_trade2 = next(row for row in rows if row["transition_display"] == "S3-S4-S5")
        self.assertEqual(li_trade2["signal_label"], "Unsupported")
        self.assertIn("memo does not provide", li_trade2["card_note"].lower())

    def test_first_optimization_stage_rows_derive_counts_from_case_files(self) -> None:
        repo = get_repository()
        rows = repo.build_stage_rows("Ni", 2024, "first_optimization", "compare")
        trade1 = next(row for row in rows if row["Stage Group"] == "S1-S2-S3")
        self.assertGreater(trade1["Countries"], 0)
        self.assertGreater(trade1["A Rows"], 0)

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
        self.assertEqual(metadata["resultModes"], ["baseline", "first_optimization"])
        self.assertEqual(metadata["resultLabels"]["first_optimization"], "First Optimization")

    def test_build_app_payload_uses_per_metal_default_reference_quantity(self) -> None:
        repo = get_repository()
        li_payload = build_app_payload(repo, "Li", 2024, "baseline", "compare", reference_qty=None, access_mode="guest")
        co_payload = build_app_payload(repo, "Co", 2024, "baseline", "compare", reference_qty=None, access_mode="guest")
        ni_payload = build_app_payload(repo, "Ni", 2024, "baseline", "compare", reference_qty=None, access_mode="guest")
        self.assertEqual(li_payload["referenceQuantity"], 50_000.0)
        self.assertEqual(co_payload["referenceQuantity"], 50_000.0)
        self.assertEqual(ni_payload["referenceQuantity"], 1_000_000.0)

    def test_default_payload_requests_hit_runtime_cache(self) -> None:
        repo = get_repository()
        clear_default_payload_cache()
        cold = build_app_payload(repo, "Ni", 2024, "baseline", "compare", access_mode="guest")
        warm = build_app_payload(repo, "Ni", 2024, "baseline", "compare", access_mode="guest")
        cache_info = default_payload_cache_info()
        self.assertEqual(cold["metal"], "Ni")
        self.assertEqual(warm["metal"], "Ni")
        self.assertGreaterEqual(cache_info["misses"], 1)
        self.assertGreaterEqual(cache_info["hits"], 1)

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
                resultMode="first_optimization",
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
        self.assertIn('"resultMode":"first_optimization"', payload)
        self.assertIn('"cobaltMode":"min"', payload)
        self.assertIn('"accessMode":"analyst"', payload)
        self.assertIn('"figure"', payload)

    def test_cobalt_second_post_trade_china_balances_in_country_payload(self) -> None:
        graphs = build_case_graphs_from_inputs_json(
            metal="Co",
            year=2024,
            scenario="baseline",
            inputs_json_path=Path("data/original/baseline/Co/2024/baseline_inputs.json"),
        )
        nodes, links = graphs["mid"]
        del nodes
        s4_china_key = "S4:country:156"
        incoming = sum(link.value for link in links if link.target == s4_china_key)
        outgoing = sum(link.value for link in links if link.source == s4_china_key)
        self.assertAlmostEqual(incoming, outgoing, places=6)

    def test_lithium_second_post_trade_country_nodes_balance_in_country_payload(self) -> None:
        graphs = build_case_graphs_from_inputs_json(
            metal="Li",
            year=2024,
            scenario="baseline",
            inputs_json_path=Path("data/original/baseline/Li/2024/baseline_inputs.json"),
        )
        nodes, links = graphs["default"]
        del nodes
        for key, delta in self._country_stage_deltas(links, "S4").items():
            self.assertAlmostEqual(delta, 0.0, places=6, msg=key)

    def test_lithium_first_post_trade_country_nodes_balance_from_inputs_for_original_and_first_optimization(self) -> None:
        roots = {
            "baseline": Path("data/original/baseline/Li"),
            "optimized": Path("data/first_optimization/optimized/Li"),
        }
        for scenario, root in roots.items():
            for year in range(2020, 2025):
                graphs = build_case_graphs_from_inputs_json(
                    metal="Li",
                    year=year,
                    scenario=scenario,
                    inputs_json_path=root / str(year) / f"{scenario}_inputs.json",
                )
                nodes, links = graphs["default"]
                del nodes
                for key, delta in self._country_stage_deltas(links, "S2").items():
                    self.assertAlmostEqual(delta, 0.0, places=6, msg=f"{scenario}-{year}-{key}")

    def test_cobalt_first_optimization_snapshot_inputs_rebuild_balances_s4_nodes_for_all_modes(self) -> None:
        root = Path("data/first_optimization/optimized/Co")
        for year in range(2020, 2025):
            graphs = build_case_graphs_from_inputs_json(
                metal="Co",
                year=year,
                scenario="optimized",
                inputs_json_path=root / str(year) / "optimized_inputs.json",
            )
            for cobalt_mode in ("mid", "max", "min"):
                nodes, links = graphs[cobalt_mode]
                del nodes
                for key, delta in self._country_stage_deltas(links, "S4").items():
                    self.assertAlmostEqual(delta, 0.0, places=6, msg=f"{year}-{cobalt_mode}-{key}")

    def test_pipeline_prefers_local_battery_7step_site_modules(self) -> None:
        cobalt_module = pipeline_v1._bundle("Co")["sankey"]
        module_path = Path(cobalt_module.__file__).resolve()
        self.assertEqual(module_path.name, "cobalt_sankey.py")
        self.assertIn("battery_7step_site", module_path.parts)
        self.assertIn("services", module_path.parts)


if __name__ == "__main__":
    unittest.main()
