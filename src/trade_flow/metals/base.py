from __future__ import annotations

from dataclasses import dataclass

from trade_flow.domain.enums import SupportLevel


@dataclass(frozen=True)
class MetalAdapter:
    metal_id: str
    slug: str
    label: str
    support_level: SupportLevel
    stages: tuple[str, ...]
    notes: str = ""
