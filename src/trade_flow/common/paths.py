from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    instance_root: Path
    conversion_factor_optimization_root: Path
    runtime_root: Path

    @property
    def conversion_factor_optimization_output_root(self) -> Path:
        return self.conversion_factor_optimization_root / "output"

    @property
    def runtime_current_root(self) -> Path:
        return self.runtime_root / "current"


def get_project_paths() -> ProjectPaths:
    project_root = Path(__file__).resolve().parents[3]
    instance_root = project_root / "instance"
    conversion_factor_optimization_root = instance_root / "conversion_factor_optimization"
    runtime_root = instance_root / "runtime"
    return ProjectPaths(
        project_root=project_root,
        instance_root=instance_root,
        conversion_factor_optimization_root=conversion_factor_optimization_root,
        runtime_root=runtime_root,
    )
