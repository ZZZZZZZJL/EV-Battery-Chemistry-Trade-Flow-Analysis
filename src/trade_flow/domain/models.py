from __future__ import annotations

from dataclasses import dataclass, field

from .enums import SupportLevel


@dataclass(frozen=True)
class MetalCapability:
    metal_id: str
    slug: str
    label: str
    support_level: SupportLevel
    stages: tuple[str, ...]
    notes: str = ""
    declared_payload_modules: tuple[str, ...] = field(default_factory=tuple)

