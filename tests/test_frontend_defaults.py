from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendDefaultTests(unittest.TestCase):
    def test_frontend_uses_single_default_app_script(self) -> None:
        template = (ROOT / "src" / "trade_flow" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("year_transition.js", template)
        self.assertIn('type="module" src="/static/js/app.js', template)
        self.assertNotIn("position-override-input", template)

    def test_app_js_does_not_reference_custom_year_transition_helper(self) -> None:
        app_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("BatteryYearTransition", app_js)
        self.assertNotIn("buildPersistentTransitionArtifacts", app_js)
        self.assertNotIn("YEAR_SWITCH_TRANSITION_MS", app_js)

    def test_custom_year_transition_helper_file_is_removed(self) -> None:
        helper_path = ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "year_transition.js"
        self.assertFalse(helper_path.exists())

    def test_frontend_interaction_modules_exist(self) -> None:
        js_root = ROOT / "src" / "trade_flow" / "web" / "static" / "js"
        for filename in (
            "app_state.js",
            "api_client.js",
            "figure_controller.js",
            "ui_shell.js",
        ):
            self.assertTrue((js_root / filename).exists(), filename)

    def test_api_client_uses_abort_controller(self) -> None:
        api_client_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "api_client.js").read_text(encoding="utf-8")
        self.assertIn("AbortController", api_client_js)
        self.assertIn("figureCache", api_client_js)

    def test_navigation_controls_match_selection_chip_contract(self) -> None:
        template = (ROOT / "src" / "trade_flow" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        app_css = (ROOT / "src" / "trade_flow" / "web" / "static" / "css" / "app.css").read_text(encoding="utf-8")
        summary_start = template.index('class="top-nav-summary"')
        summary_end = template.index('class="top-nav-panel"')
        summary_markup = template[summary_start:summary_end]

        self.assertIn('id="metal-buttons"', summary_markup)
        self.assertIn('id="year-buttons"', summary_markup)
        self.assertIn('id="result-buttons"', summary_markup)
        self.assertIn('id="cobalt-mode-buttons"', summary_markup)
        self.assertNotIn('class="nav-action-icon"', summary_markup)
        self.assertNotIn("advanced-panel", template)
        self.assertIn('class="normal-controls-grid"', template)
        self.assertIn('id="top-nav-controls-toggle"', template)
        self.assertIn('id="top-nav-panel"', template)
        self.assertNotIn("Ni, Li, and Co are active", template)
        self.assertNotIn('id="metal-note"', template)
        first_row = [
            template.index('class="control-block control-block-theme"'),
            template.index('class="dock-group dock-group-s7"'),
            template.index('class="control-block control-block-reference"'),
        ]
        second_row = [
            template.index('class="control-block control-block-access"'),
            template.index('id="refresh-btn"'),
            template.index('id="download-btn"'),
        ]
        self.assertEqual(first_row, sorted(first_row))
        self.assertEqual(second_row, sorted(second_row))
        self.assertNotIn('class="dock-actions"', template)
        self.assertIn("is-analysis-controls", app_js)
        self.assertIn(".top-nav-details.is-analysis-controls .dock-group-s7", app_css)
        self.assertIn(".top-nav-details.is-analysis-controls .control-block-reference", app_css)
        self.assertIn(".top-nav-details.is-analysis-controls .control-action-btn", app_css)
        self.assertIn('body[data-workspace-view="vulnerability"] .top-nav-selection-group', app_css)

    def test_analysis_workspace_menu_splits_optimization_and_vulnerability(self) -> None:
        template = (ROOT / "src" / "trade_flow" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="analysis-workspace-menu"', template)
        self.assertIn('data-selection-menu-trigger="analysis-workspace"', template)
        self.assertIn('data-workspace-view="analysis"', template)
        self.assertIn('data-workspace-view="vulnerability"', template)
        self.assertIn('href="#vulnerability-board"', template)
        self.assertIn('id="vulnerability-board"', template)
        self.assertNotIn('id="vulnerability-score-cards"', template)
        self.assertNotIn("Method Case Comparison", template)
        self.assertNotIn("Method Note", template)
        self.assertNotIn('id="vulnerability-ranking-table"', template)
        self.assertNotIn('id="vulnerability-case-table"', template)
        self.assertIn('id="vulnerability-case-guide"', template)
        self.assertIn('id="vulnerability-country-vi-country-select"', app_js)
        self.assertIn("Target country", app_js)
        self.assertIn('id="vulnerability-country-vi-metal-select"', app_js)
        self.assertIn("VI metal", app_js)
        self.assertIn('id="vulnerability-country-vi-material-select"', app_js)
        self.assertIn("Material type", app_js)
        self.assertIn("NCX", app_js)
        self.assertIn('id="vulnerability-country-vi-year-select"', app_js)
        self.assertIn("Profile year", app_js)
        self.assertNotIn('id="vulnerability-trend-country-select"', app_js)
        self.assertNotIn("Trend country", app_js)
        self.assertNotIn('id="vulnerability-trend-pair-select"', app_js)
        self.assertNotIn("Trend pair", app_js)
        self.assertIn('class="order-card-head vulnerability-trend-toolbar"', template)
        self.assertIn('id="vulnerability-trend-compare-country-select"', app_js)
        self.assertIn('id="vulnerability-trend-add-country-btn"', app_js)
        self.assertNotIn('class="vulnerability-country-control"', template)
        self.assertIn('id="vulnerability-country-line-legend"', app_js)
        self.assertIn("vulnerability-trend-legend-deck", app_js)
        self.assertIn('id="vulnerability-trend-charts"', template)
        self.assertIn('id="vulnerability-sensitivity-panel"', template)
        self.assertNotIn('id="vulnerability-delta-table"', template)
        self.assertIn("buildVulnerabilityCountryResultComparisonHtml", app_js)
        self.assertIn("Keep this table to the exact VI method values only", app_js)
        self.assertNotIn("Base vs Original", app_js)
        workspace_block = app_js[app_js.index("function applyWorkspaceView"):app_js.index("function showWorkspaceView")]
        self.assertIn("fresh draw pass after the section becomes visible", workspace_block)
        self.assertIn("scheduleVulnerabilityStageProfilePlot();", workspace_block)
        self.assertIn("scheduleVulnerabilityTrendPlots();", workspace_block)
        self.assertIn("scheduleVulnerabilitySensitivityStageProfilePlot();", workspace_block)
        self.assertNotIn('id="vulnerability-method-note"', template)
        trend_index = template.index('id="vulnerability-trend-charts"')
        sensitivity_index = template.index('id="vulnerability-sensitivity-panel"')
        self.assertLess(trend_index, sensitivity_index)
        self.assertIn('#vulnerability-board', app_js)
        self.assertIn('"vulnerability"', app_js)

    def test_vulnerability_country_rankings_cover_all_result_cases(self) -> None:
        data_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "vulnerability_data.js").read_text(encoding="utf-8")
        country_rows_start = data_js.index("countryRows")
        top_deltas_start = data_js.index("topDeltas")
        country_rows = data_js[country_rows_start:top_deltas_start]

        for result_mode in ("baseline", "pareto_optimal", "sn_minimum", "deviation_minimum"):
            self.assertIn(f'resultMode: "{result_mode}"', country_rows)
        for metal in ("Ni", "Li", "Co"):
            self.assertIn(f'metal: "{metal}"', country_rows)
        self.assertGreater(country_rows.count("country:"), 150)

        app_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("Ni 2024 Pareto Optimal first-release slice", app_js)

    def test_vulnerability_country_trends_cover_years_and_results(self) -> None:
        data_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "vulnerability_data.js").read_text(encoding="utf-8")
        self.assertIn("countryTrendRows", data_js)
        self.assertIn("countryPairTrendRows", data_js)
        self.assertIn('materialPair: "NMC-Ni"', data_js)
        self.assertIn('materialPair: "NCA-Ni"', data_js)
        trend_start = data_js.index("countryTrendRows")
        trend_rows = data_js[trend_start:]

        for result_mode in ("baseline", "pareto_optimal", "sn_minimum", "deviation_minimum"):
            self.assertIn(f'resultMode: "{result_mode}"', trend_rows)
        for year in (2020, 2021, 2022, 2023, 2024):
            self.assertIn(f"year: {year}", trend_rows)
        self.assertIn('country: "China"', trend_rows)
        self.assertGreater(trend_rows.count("country:"), 500)

        app_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("renderVulnerabilityCountryTrend", app_js)
        self.assertIn("renderVulnerabilityTrendPlots", app_js)
        self.assertIn("Plotly.react", app_js)
        self.assertIn("hovertemplate", app_js)
        self.assertIn("data-vulnerability-series", app_js)
        self.assertIn("vulnerabilityCompareCountries", app_js)
        self.assertIn("data-vulnerability-remove-country", app_js)
        self.assertIn("VULNERABILITY_CASE_GUIDE", app_js)
        self.assertIn("buildVulnerabilityCountryLineLegendHtml", app_js)
        self.assertIn("vulnerability-country-line-legend", app_js)
        self.assertIn("vulnerabilityPairOptionsForCountry", app_js)
        self.assertIn('pareto_optimal: "Multiobjective"', app_js)
        self.assertNotIn('label: "Pareto Optimal"', app_js)
        self.assertNotIn("vulnerability-current-year", app_js)
        self.assertNotIn('text: "Current"', app_js)
        self.assertNotIn("showCurrentYear", app_js)
        self.assertNotIn("buildTrendPolyline", app_js)
        self.assertNotIn("vulnerability-line-chart", app_js)

    def test_vulnerability_sensitivity_lab_is_non_guest_sandbox(self) -> None:
        app_js = (ROOT / "src" / "trade_flow" / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")

        self.assertIn("vulnerabilitySensitivity", app_js)
        self.assertIn("VULNERABILITY_SENSITIVITY_STEPS", app_js)
        self.assertIn("buildVulnerabilitySensitivityPanelHtml", app_js)
        self.assertIn("renderVulnerabilitySensitivityPanel", app_js)
        self.assertIn('state.accessMode !== "analyst"', app_js)
        self.assertIn("vulnerability-sensitivity-lock", app_js)
        self.assertIn("vulnerability-production-editor", app_js)
        self.assertIn("vulnerability-sensitivity-step-select", app_js)
        self.assertIn("vulnerability-sensitivity-metal-select", app_js)
        self.assertIn("vulnerability-sensitivity-material-select", app_js)
        self.assertIn("pair: sensitivity.selectedPair", app_js)
        self.assertIn("vulnerability-sensitivity-recalculate-btn", app_js)
        self.assertIn("Scenario Output", app_js)
        self.assertIn("Recalculate VI", app_js)


if __name__ == "__main__":
    unittest.main()
