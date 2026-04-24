from __future__ import annotations

from trade_flow.metals.cobalt.spec import ADAPTER as COBALT_ADAPTER
from trade_flow.metals.graphite.spec import ADAPTER as GRAPHITE_ADAPTER
from trade_flow.metals.lithium.spec import ADAPTER as LITHIUM_ADAPTER
from trade_flow.metals.manganese.spec import ADAPTER as MANGANESE_ADAPTER
from trade_flow.metals.nickel.spec import ADAPTER as NICKEL_ADAPTER
from trade_flow.metals.phosphorus.spec import ADAPTER as PHOSPHORUS_ADAPTER


_REGISTRY = {
    adapter.metal_id: adapter
    for adapter in (
        LITHIUM_ADAPTER,
        NICKEL_ADAPTER,
        COBALT_ADAPTER,
        MANGANESE_ADAPTER,
        GRAPHITE_ADAPTER,
        PHOSPHORUS_ADAPTER,
    )
}


def iter_supported_metals():
    return [_REGISTRY[key] for key in ("Li", "Ni", "Co", "Mn", "Graphite", "Phosphorus")]


def get_supported_metal(metal_id: str):
    return _REGISTRY[metal_id]
