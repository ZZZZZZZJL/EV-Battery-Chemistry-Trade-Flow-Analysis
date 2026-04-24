from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import RUNTIME_SCHEMA_VERSION


@dataclass(frozen=True)
class RuntimeBundleManifest:
    data_release_id: str
    built_at: str
    public_code_commit: str
    private_pipeline_tag: str
    algorithms: list[str] = field(default_factory=list)
    metals: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)
    schema_version: str = RUNTIME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "data_release_id": self.data_release_id,
            "built_at": self.built_at,
            "public_code_commit": self.public_code_commit,
            "private_pipeline_tag": self.private_pipeline_tag,
            "algorithms": list(self.algorithms),
            "metals": list(self.metals),
            "years": list(self.years),
            "hashes": dict(self.hashes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeBundleManifest":
        return cls(
            schema_version=str(payload.get("schema_version", RUNTIME_SCHEMA_VERSION)),
            data_release_id=str(payload.get("data_release_id", "")),
            built_at=str(payload.get("built_at", "")),
            public_code_commit=str(payload.get("public_code_commit", "")),
            private_pipeline_tag=str(payload.get("private_pipeline_tag", "")),
            algorithms=[str(item) for item in payload.get("algorithms", [])],
            metals=[str(item) for item in payload.get("metals", [])],
            years=[int(item) for item in payload.get("years", [])],
            hashes={str(key): str(value) for key, value in dict(payload.get("hashes", {})).items()},
        )

