from __future__ import annotations

import unittest

from trade_flow_opt import pipeline_v3 as pipeline
from trade_flow_opt.pipeline_v1 import TransitionContext, TransitionSpec
from trade_flow_opt.v3_config import HS_ROLE_CONFIG, HSRoleSpec


class PipelineV3Tests(unittest.TestCase):
    def test_synthetic_li_trade2_folder_stays_out_of_v3_optimization(self) -> None:
        self.assertFalse(HS_ROLE_CONFIG["2nd_post_trade/Li_000000"].optimize)

    def test_asymmetric_regularization_penalizes_small_uplift_more_than_small_downshift(self) -> None:
        params = pipeline.HyperParameters(0.05, 0.05, 0.06, 0.24, 0.03, 0.26, 0.03, 0.05, 0.06, 0.06, 0.05, 1)
        pn_up = pipeline._regularization_cost("PN", 1.03, 1.0, params)
        pn_down = pipeline._regularization_cost("PN", 0.97, 1.0, params)
        np_up = pipeline._regularization_cost("NP", 1.03, 1.0, params)
        np_down = pipeline._regularization_cost("NP", 0.97, 1.0, params)
        self.assertGreater(pn_up, pn_down)
        self.assertGreater(np_up, np_down)

    def test_shared_transition_supply_cap_scales_multiple_real_hs_folders(self) -> None:
        spec = HSRoleSpec(
            optimize=True,
            source_fields=("processing_total",),
            target_fields=("refining_mid",),
            use_transition_supply_cap=True,
        )
        folder_a = "dummy_a"
        folder_b = "dummy_b"
        folder_data = {
            year: {
                folder_a: pipeline.FolderYearData(
                    folder_name=folder_a,
                    spec=spec,
                    raw_map={(1, 2): 80.0},
                    edge_classes={(1, 2): "PP"},
                    source_producers={1},
                    target_producers={2},
                    exact_source_cap_map={},
                    raw_total=80.0,
                    edge_count_by_class={"PP": 1, "PN": 0, "NP": 0, "NN": 0},
                ),
                folder_b: pipeline.FolderYearData(
                    folder_name=folder_b,
                    spec=spec,
                    raw_map={(1, 3): 70.0},
                    edge_classes={(1, 3): "PP"},
                    source_producers={1},
                    target_producers={3},
                    exact_source_cap_map={},
                    raw_total=70.0,
                    edge_count_by_class={"PP": 1, "PN": 0, "NP": 0, "NN": 0},
                ),
            }
            for year in pipeline.YEARS
        }
        context_by_year = {
            year: TransitionContext(
                key="trade2",
                source_stage="S3",
                post_stage="S4",
                target_stage="S5",
                source_totals={1: 100.0},
                trade_supply={1: 100.0},
                direct_local={},
                balance_map={},
                target_totals={2: 60.0, 3: 40.0},
                folder_names=(folder_a, folder_b),
                input_fields=("trade2",),
            )
            for year in pipeline.YEARS
        }
        series = pipeline.TransitionSeries(
            metal="Co",
            transition_spec=TransitionSpec(
                key="trade2",
                source_stage="S3",
                post_stage="S4",
                target_stage="S5",
                folder_names=(folder_a, folder_b),
                input_fields=("trade2",),
            ),
            context_by_year=context_by_year,
            folder_data_by_year=folder_data,
            coefficient_meta={},
            coefficient_order=[],
            exposure_by_key_year={},
            total_raw_by_year={year: 150.0 for year in pipeline.YEARS},
        )
        folder_maps = pipeline._build_year_folder_maps(series, pipeline.YEARS[0], {})
        total = sum(sum(edge_map.values()) for edge_map in folder_maps.values())
        self.assertAlmostEqual(total, 100.0, places=6)
        self.assertAlmostEqual(folder_maps[folder_a][(1, 2)] / folder_maps[folder_b][(1, 3)], 80.0 / 70.0, places=6)

    def test_transition_cost_blocks_year_jump_above_spec_delta_when_exposure_exists(self) -> None:
        spec = HSRoleSpec(
            optimize=True,
            source_fields=("refining_hydroxide",),
            target_fields=("cathode_ncm",),
            pp_delta=0.10,
        )
        key = pipeline.CoefficientKey("PP", "dummy", exporter=1, importer=2)
        series = pipeline.TransitionSeries(
            metal="Li",
            transition_spec=TransitionSpec("trade3", "S5", "S6", "S7", ("dummy",), ("trade3",)),
            context_by_year={year: TransitionContext("trade3", "S5", "S6", "S7", {}, {}, {}, {}, {}, ("dummy",), ("trade3",)) for year in pipeline.YEARS},
            folder_data_by_year={year: {} for year in pipeline.YEARS},
            coefficient_meta={key: {"spec": spec}},
            coefficient_order=[key],
            exposure_by_key_year={key: {pipeline.YEARS[0]: 10.0, pipeline.YEARS[1]: 12.0}},
            total_raw_by_year={pipeline.YEARS[0]: 20.0, pipeline.YEARS[1]: 20.0, pipeline.YEARS[2]: 0.0, pipeline.YEARS[3]: 0.0, pipeline.YEARS[4]: 0.0},
        )
        params = pipeline.HyperParameters(0.05, 0.05, 0.06, 0.24, 0.03, 0.26, 0.03, 0.05, 0.06, 0.06, 0.05, 1)
        self.assertIsNone(
            pipeline._transition_cost(series, key, pipeline.YEARS[0], pipeline.YEARS[1], 1.00, 1.20, params)
        )


if __name__ == "__main__":
    unittest.main()
