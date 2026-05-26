from __future__ import annotations

import unittest

from trade_flow.legacy_site.services.shared_sankey import (
    DEFAULT_SPECIAL_POSITION,
    DEFAULT_SORT_MODE,
    LinkSpec,
    NodeSpec,
    _apply_stage_aggregation,
    _validate_aggregate_preserve,
)


class AggregatePreserveTests(unittest.TestCase):
    def test_preserved_tail_country_is_not_collapsed(self) -> None:
        nodes = {
            "S1:a": NodeSpec("S1:a", "S1", "Alpha", "#111111", "regular", "Alpha", "Asia"),
            "S1:b": NodeSpec("S1:b", "S1", "Beta", "#222222", "regular", "Beta", "Asia"),
            "S1:c": NodeSpec("S1:c", "S1", "Gamma", "#333333", "regular", "Gamma", "Asia"),
            "S2:x": NodeSpec("S2:x", "S2", "Sink", "#444444", "regular", "Sink", "Asia"),
        }
        links = [
            LinkSpec("S1:a", "S2:x", 30.0, "#111111"),
            LinkSpec("S1:b", "S2:x", 20.0, "#222222"),
            LinkSpec("S1:c", "S2:x", 10.0, "#333333"),
        ]
        sort_modes = {"S1": DEFAULT_SORT_MODE}
        special_positions = {"S1": DEFAULT_SPECIAL_POSITION}
        aggregate_preserve = _validate_aggregate_preserve(nodes, {"S1": ["S1:c"]})

        figure_nodes, figure_links = _apply_stage_aggregation(
            nodes,
            links,
            sort_modes,
            {},
            special_positions,
            {"S1": 1},
            aggregate_preserve,
            "country",
            1e-9,
        )

        self.assertIn("S1:c", figure_nodes)
        self.assertIn("S1:aggregate:tail", figure_nodes)
        self.assertNotIn("S1:b", figure_nodes)
        self.assertTrue(any(link.source == "S1:aggregate:tail" for link in figure_links))


if __name__ == "__main__":
    unittest.main()
