from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from battery_7step_site.config import BatterySiteConfig, get_battery_site_config
from battery_7step_site.services.datasets import load_dataset_config


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
    checks: list[RuntimeCheck] = [
        _path_check("templates", "Templates", config.templates_dir),
        _path_check("static", "Static Assets", config.static_dir),
        _path_check("output", "Active Output Directory", config.output_dir),
        _path_check("output_versions", "Output Versions Root", config.output_versions_root),
    ]
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
                _path_check("production_root", "Production Root", Path(dataset_config["productionRoot"])),
                _path_check("trade_root", "Trade Root", Path(dataset_config["tradeRoot"])),
            ]
        )

    if config.analyst_password == "88888888":
        warnings.append("Analyst password is using the local-development default.")

    for check in checks:
        if check.required and not check.exists:
            errors.append(f"Missing required runtime resource: {check.label}")

    ready = not errors
    return RuntimeStatus(
        ready=ready,
        checks=tuple(checks),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )

