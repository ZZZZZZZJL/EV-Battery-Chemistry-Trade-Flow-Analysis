from __future__ import annotations

import os
import unittest

from trade_flow.runtime.repository import get_repository
from trade_flow.web.api.bootstrap import bootstrap
from trade_flow.web.api.sankey import FigureRequestModel, figure
from trade_flow.web.main import healthz


_PRIVATE_INTEGRATION_ENABLED = os.getenv("TRADE_FLOW_ENABLE_PRIVATE_INTEGRATION_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


@unittest.skipUnless(
    _PRIVATE_INTEGRATION_ENABLED,
    "Private integration tests are opt-in after the public repo runtime data was moved to production_data_processing.",
)
class WebViewerIntegrationTests(unittest.TestCase):
    def test_repository_detects_runtime_payloads(self) -> None:
        repo = get_repository()
        self.assertGreater(len(repo.metals), 0)
        self.assertGreater(len(repo.years), 0)

    def test_healthz_reports_ready(self) -> None:
        response = healthz()
        self.assertEqual(response.status_code, 200)
        self.assertIn('"ready":true', response.body.decode("utf-8"))

    def test_bootstrap_and_figure_work_against_private_runtime(self) -> None:
        payload = bootstrap()
        metadata = payload["metadata"]
        response = figure(
            FigureRequestModel(
                metal=metadata["defaultMetal"],
                year=metadata["defaultYear"],
                theme=metadata["defaultTheme"],
                resultMode="baseline",
                tableView="auto",
                referenceQuantity=float(metadata["defaultReferenceQuantity"]),
                sortModes={},
                stageOrders={},
                specialPositions={},
                aggregateCounts={},
                cobaltMode=metadata["defaultCobaltMode"],
                accessMode=metadata["defaultAccessMode"],
                accessPassword="",
            )
        )
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn('"figure"', body)
        self.assertIn('"metal"', body)


if __name__ == "__main__":
    unittest.main()
