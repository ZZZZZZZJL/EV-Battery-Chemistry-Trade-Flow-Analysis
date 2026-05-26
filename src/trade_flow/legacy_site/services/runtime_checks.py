from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trade_flow.legacy_site.config import BatterySiteConfig, get_battery_site_config
from trade_flow.legacy_site.services.datasets import load_dataset_config
from trade_flow.legacy_site.services.precomputed_repository import OPTIMIZATION_DATA_DIRS, SCENARIO_LABELS


@dataclass(frozen=True)
class RuntimeCheck:
    key: str
    label: str
    exists: bool
    required: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "exists": self.exists,
            "required": self.required,
        }


@dataclass(frozen=True)
class RuntimeStatus:
    ready: bool
    checks: tuple[RuntimeCheck, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks": [check.to_public_dict() for check in self.checks],
        }


def _path_check(key: str, label: str, path: Path, required: bool = True) -> RuntimeCheck:
    return RuntimeCheck(key=key, label=label, exists=path.exists(), required=required)


def gather_runtime_status(config: BatterySiteConfig | None = None) -> RuntimeStatus:
    config = config or get_battery_site_config()
    local_output_root = config.root_dir / "output"
    original_root = config.original_data_root if (config.original_data_root / "baseline").exists() else local_output_root
    first_optimization_root = (
        config.first_optimization_data_root
        if (config.first_optimization_data_root / "optimized").exists()
        else local_output_root
    )
    diagnostics_root = (
        config.first_optimization_diagnostics_root
        if config.first_optimization_diagnostics_root.exists()
        else config.instance_dir / "conversion_factor_optimization" / "output"
    )
    checks: list[RuntimeCheck] = [
        _path_check("templates", "Templates", config.templates_dir),
        _path_check("static", "Static Assets", config.static_dir),
        _path_check("data_dir", "App Data Directory", config.data_dir),
        _path_check("original_cases", "Original Case Root", original_root),
    ]
    for scenario, directory_name in OPTIMIZATION_DATA_DIRS.items():
        scenario_root = config.data_dir / directory_name
        resolved_root = scenario_root if (scenario_root / "optimized").exists() else first_optimization_root
        scenario_diagnostics_root = scenario_root / "diagnostics"
        resolved_diagnostics_root = scenario_diagnostics_root if scenario_diagnostics_root.exists() else diagnostics_root
        scenario_label = SCENARIO_LABELS.get(scenario, scenario)
        checks.extend(
            [
                _path_check(f"{scenario}_cases", f"{scenario_label} Case Root", resolved_root),
                _path_check(f"{scenario}_diagnostics", f"{scenario_label} Diagnostics Root", resolved_diagnostics_root, required=False),
            ]
        )
    errors: list[str] = []
    warnings: list[str] = []

    try:
        dataset_config = load_dataset_config()
    except Exception as exc:  # pragma: no cover - guarded by tests through healthy local config
        dataset_config = None
        errors.append(f"Dataset configuration could not be loaded: {exc}")

    if dataset_config is not None:
        checks.extend(
            [
                _path_check("reference_file", "Reference File", Path(dataset_config["referenceFile"])),
            ]
        )

    if config.analyst_password == "88888888":
        warnings.append("Analyst password is using the local-development default.")

    for check in checks:
        if check.required and not check.exists:
            errors.append(f"Missing required runtime resource: {check.label}")
        elif not check.required and not check.exists:
            warnings.append(f"Optional runtime resource unavailable: {check.label}")

    ready = not errors
    return RuntimeStatus(
        ready=ready,
        checks=tuple(checks),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )

