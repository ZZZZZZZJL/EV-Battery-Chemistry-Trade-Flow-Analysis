from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from trade_flow.runtime.dataset_registry import build_dataset_registry


class DatasetRegistryTests(unittest.TestCase):
    @patch("trade_flow.runtime.dataset_registry.get_repository")
    def test_dataset_registry_reports_support_levels(self, mock_get_repository) -> None:
        mock_get_repository.return_value = SimpleNamespace(metals=["Li", "Ni", "Co"])
        registry = build_dataset_registry()
        self.assertTrue(any(item["id"] == "Li" and item["supportLevel"] == "full" for item in registry))
        self.assertTrue(any(item["id"] == "Mn" and item["supportLevel"] == "partial" for item in registry))
        self.assertTrue(any(item["id"] == "Graphite" and item["availability"] == "planned" for item in registry))


if __name__ == "__main__":
    unittest.main()
