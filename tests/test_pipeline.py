from __future__ import annotations

from pathlib import Path
import unittest

from trade_flow.baseline import (
    HyperParameters,
    TransitionContext,
    apply_reexport,
    build_country_graph,
    evaluate_transition,
    load_year_inputs,
    optimize_transition,
    transition_contexts,
)


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_external_baseline_builds(self):
        mining_workbook = ROOT / "data" / "shared" / "production" / "country" / "Lithium_Mining_Final.xlsx"
        if not mining_workbook.exists() or mining_workbook.stat().st_size == 0:
            self.skipTest("Public repo does not currently ship non-empty lithium workbook fixtures.")
        inputs = load_year_inputs("Li", 2024)
        nodes, links = build_country_graph("Li", 2024, inputs=inputs)
        self.assertTrue(nodes)
        self.assertTrue(links)
        self.assertEqual(set(transition_contexts("Li", inputs)), {"trade1", "trade2", "trade3"})

    def test_reexport_conserves_total(self):
        flow_map = {(1, 2): 50.0, (2, 3): 100.0}
        adjusted = apply_reexport(flow_map, supply_map={2: 20.0}, direct_local={}, hub_threshold=1.0, reexport_cap=0.5)
        self.assertAlmostEqual(sum(flow_map.values()), sum(adjusted.values()))
        self.assertAlmostEqual(adjusted.get((1, 3), 0.0), 50.0)
        self.assertAlmostEqual(adjusted.get((2, 3), 0.0), 50.0)

    def test_transition_optimizer_reduces_unknown(self):
        context = TransitionContext(
            key="trade1",
            source_stage="S1",
            post_stage="S2",
            target_stage="S3",
            source_totals={1: 100.0},
            trade_supply={1: 80.0},
            direct_local={},
            balance_map={2: 20.0},
            target_totals={2: 100.0},
            folder_names=("dummy",),
            input_fields=("trade1",),
        )
        params = HyperParameters(0.75, 0.0, 1.1, 0.0, 1, 0.8, 1.2, 0.1, 1, 0.1, 0.02, 0.02)
        baseline = evaluate_transition({(1, 2): 120.0}, context)
        _optimized_map, _multipliers, optimized = optimize_transition({(1, 2): 120.0}, context, params)
        self.assertLessEqual(optimized["unknown_total"], baseline["unknown_total"])


if __name__ == "__main__":
    unittest.main()
