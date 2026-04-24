from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from trade_flow.web.api.bootstrap import bootstrap


class ApiBootstrapTests(unittest.TestCase):
    @patch("trade_flow.web.presenters.sankey_presenter.get_repository")
    def test_bootstrap_exposes_expected_defaults(self, mock_get_repository) -> None:
        mock_get_repository.return_value = SimpleNamespace(metals=["Ni"], years=[2024])
        payload = bootstrap()
        metadata = payload["metadata"]
        self.assertEqual(metadata["defaultTheme"], "light")
        self.assertIn("baseline", metadata["resultModes"])
        self.assertIn("first_optimization", metadata["resultModes"])
        self.assertEqual(metadata["defaultMetal"], "Ni")
        self.assertEqual(metadata["defaultYear"], 2024)


if __name__ == "__main__":
    unittest.main()
