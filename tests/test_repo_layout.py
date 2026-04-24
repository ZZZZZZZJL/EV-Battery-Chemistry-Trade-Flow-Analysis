from __future__ import annotations

from pathlib import Path
import unittest

from apps.web.app import app as web_app
from trade_flow.common.paths import get_project_paths
from trade_flow.web.main import app as canonical_app


ROOT = Path(__file__).resolve().parents[1]


class RepoLayoutTests(unittest.TestCase):
    def test_apps_entrypoint_targets_canonical_web_app(self) -> None:
        self.assertIs(web_app, canonical_app)

    def test_formal_structure_exists(self) -> None:
        required = [
            ROOT / "src" / "trade_flow" / "web" / "main.py",
            ROOT / "src" / "trade_flow" / "domain" / "paths.py",
            ROOT / "src" / "trade_flow" / "runtime" / "bundle_loader.py",
            ROOT / "docs" / "runbooks" / "render-deploy.md",
            ROOT / "schemas" / "runtime_bundle.schema.json",
            ROOT / "fixtures",
        ]
        for path in required:
            self.assertTrue(path.exists(), path)

    def test_project_paths_keep_instance_workspace_contract(self) -> None:
        paths = get_project_paths()
        self.assertEqual(paths.conversion_factor_optimization_root.name, "conversion_factor_optimization")
        self.assertEqual(paths.conversion_factor_optimization_root.parent.name, "instance")


if __name__ == "__main__":
    unittest.main()
