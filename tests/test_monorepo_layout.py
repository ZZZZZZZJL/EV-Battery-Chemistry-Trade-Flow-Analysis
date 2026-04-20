from __future__ import annotations

import unittest

from apps.web.app import app as web_app
from battery_7step_site.main import app as site_app
from trade_flow.common.paths import get_project_paths
from trade_flow.conversion_factor_optimization import ObjectiveWeights, run_conversion_factor_optimization


class MonorepoLayoutTests(unittest.TestCase):
    def test_apps_web_entrypoint_wraps_site_app(self) -> None:
        self.assertIs(web_app, site_app)

    def test_conversion_factor_optimization_exports_formal_api(self) -> None:
        self.assertTrue(callable(run_conversion_factor_optimization))
        self.assertAlmostEqual(ObjectiveWeights().alpha, 1.0)

    def test_project_paths_use_instance_backed_optimizer_workspace(self) -> None:
        paths = get_project_paths()
        self.assertEqual(paths.conversion_factor_optimization_root.name, "conversion_factor_optimization")
        self.assertEqual(paths.conversion_factor_optimization_root.parent.name, "instance")


if __name__ == "__main__":
    unittest.main()
