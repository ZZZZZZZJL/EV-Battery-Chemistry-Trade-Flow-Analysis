from __future__ import annotations

import unittest

from trade_flow_opt import pipeline_v2 as pipeline
from trade_flow_opt.pipeline_v1 import TransitionContext


class PipelineV2Tests(unittest.TestCase):
    def _context(self) -> TransitionContext:
        return TransitionContext(
            key="tradeX",
            source_stage="S1",
            post_stage="S2",
            target_stage="S3",
            source_totals={1: 100.0, 3: 40.0, 4: 0.0},
            trade_supply={1: 100.0, 3: 40.0, 4: 0.0},
            direct_local={},
            balance_map={},
            target_totals={2: 50.0, 3: 20.0, 4: 0.0},
            folder_names=("dummy",),
            input_fields=("trade1",),
        )

    def test_country_roles_follow_fixed_production_logic(self) -> None:
        roles = pipeline._country_roles(self._context())
        self.assertEqual(roles[1], "source")
        self.assertEqual(roles[2], "target")
        self.assertEqual(roles[3], "dual")
        self.assertEqual(roles[4], "trader")

    def test_reconstruct_trade_flow_reassigns_trader_exports_to_true_origin(self) -> None:
        params = pipeline.HyperParameters(0.8, 0.0, 0.7, 6, 3, 0.75, 1.25, 0.85, 1.15, 0.1, 2, 0.1, 0.03, 0.03, 0.05)
        context = TransitionContext(
            key="tradeX",
            source_stage="S1",
            post_stage="S2",
            target_stage="S3",
            source_totals={1: 100.0},
            trade_supply={1: 100.0},
            direct_local={},
            balance_map={},
            target_totals={3: 60.0},
            folder_names=("dummy",),
            input_fields=("trade1",),
        )
        flow_map = {(1, 2): 80.0, (2, 3): 60.0}
        reconstructed, next_inventory, diagnostics = pipeline.reconstruct_trade_flow_v2(flow_map, context, {}, params)
        self.assertAlmostEqual(reconstructed[(1, 2)], 20.0, places=6)
        self.assertAlmostEqual(reconstructed[(1, 3)], 60.0, places=6)
        self.assertNotIn((2, 3), reconstructed)
        self.assertAlmostEqual(next_inventory[2][1], 20.0, places=6)
        self.assertAlmostEqual(diagnostics["transit_reallocated_total"], 60.0, places=6)

    def test_apply_alpha_scales_respects_source_supply_cap(self) -> None:
        params = pipeline.HyperParameters(0.8, 0.0, 0.7, 6, 3, 0.75, 1.25, 0.85, 1.15, 0.1, 2, 0.1, 0.03, 0.03, 0.05)
        context = TransitionContext(
            key="tradeX",
            source_stage="S1",
            post_stage="S2",
            target_stage="S3",
            source_totals={1: 100.0},
            trade_supply={1: 100.0},
            direct_local={},
            balance_map={},
            target_totals={2: 90.0, 3: 40.0},
            folder_names=("dummy",),
            input_fields=("trade1",),
        )
        roles = pipeline._country_roles(context)
        scaled = pipeline._apply_alpha_scales({(1, 2): 80.0, (1, 3): 50.0}, {1: 1.3}, context, roles)
        self.assertAlmostEqual(sum(scaled.values()), 100.0, places=6)
        self.assertAlmostEqual(scaled[(1, 2)] / scaled[(1, 3)], 80.0 / 50.0, places=6)
        self.assertIn(1.0, params.values_for_role("source"))


if __name__ == "__main__":
    unittest.main()
