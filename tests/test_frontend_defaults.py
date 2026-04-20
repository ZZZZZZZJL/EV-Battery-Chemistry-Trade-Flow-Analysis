from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendDefaultTests(unittest.TestCase):
    def test_frontend_uses_single_default_app_script(self) -> None:
        template = (ROOT / "battery_7step_site" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("year_transition.js", template)

    def test_app_js_does_not_reference_custom_year_transition_helper(self) -> None:
        app_js = (ROOT / "battery_7step_site" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("BatteryYearTransition", app_js)
        self.assertNotIn("buildPersistentTransitionArtifacts", app_js)
        self.assertNotIn("YEAR_SWITCH_TRANSITION_MS", app_js)

    def test_custom_year_transition_helper_file_is_removed(self) -> None:
        helper_path = ROOT / "battery_7step_site" / "static" / "js" / "year_transition.js"
        self.assertFalse(helper_path.exists())


if __name__ == "__main__":
    unittest.main()
