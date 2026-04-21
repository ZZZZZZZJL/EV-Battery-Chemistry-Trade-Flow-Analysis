from __future__ import annotations

import unittest

from trade_flow.metals.registry import get_supported_metal, iter_supported_metals


class MetalRegistryTests(unittest.TestCase):
    def test_registry_contains_full_and_partial_support(self) -> None:
        metals = iter_supported_metals()
        ids = [metal.metal_id for metal in metals]
        self.assertEqual(ids[:3], ["Li", "Ni", "Co"])
        self.assertIn("Mn", ids)

    def test_get_supported_metal_returns_declared_adapter(self) -> None:
        adapter = get_supported_metal("Li")
        self.assertEqual(adapter.slug, "lithium")
        self.assertEqual(adapter.support_level.value, "full")


if __name__ == "__main__":
    unittest.main()
