from __future__ import annotations

from trade_flow.metals.registry import iter_supported_metals
from trade_flow.runtime.repository import get_repository


def build_dataset_registry() -> list[dict[str, str]]:
    repo = get_repository()
    available_metals = set(repo.metals)
    return [
        {
            "id": capability.metal_id,
            "slug": capability.slug,
            "label": capability.label,
            "supportLevel": capability.support_level.value,
            "availability": "available" if capability.metal_id in available_metals else "planned",
        }
        for capability in iter_supported_metals()
    ]
