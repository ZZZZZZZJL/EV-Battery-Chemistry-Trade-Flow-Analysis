from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from trade_flow.domain.paths import get_runtime_paths


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BatterySiteConfig:
    root_dir: Path
    package_dir: Path
    instance_dir: Path
    templates_dir: Path
    static_dir: Path
    data_dir: Path
    reference_file_path: Path
    shared_data_root: Path
    original_data_root: Path
    first_optimization_data_root: Path
    first_optimization_diagnostics_root: Path
    dataset_config_path: Path
    output_versions_root: Path
    runtime_root: Path
    runtime_release_root: Path
    analyst_password: str
    strict_startup: bool


def get_battery_site_config() -> BatterySiteConfig:
    root_dir = Path(__file__).resolve().parents[3]
    runtime_paths = get_runtime_paths(project_root=root_dir)
    package_dir = runtime_paths.web_package_root
    data_dir = Path(os.getenv("BATTERY_SITE_APP_DATA_DIR", str(runtime_paths.app_data_root))).resolve()
    instance_dir = Path(os.getenv("BATTERY_SITE_INSTANCE_DIR", str(root_dir / "instance"))).resolve()
    instance_dir.mkdir(parents=True, exist_ok=True)
    dataset_config_path = Path(
        os.getenv("BATTERY_SITE_DATASET_CONFIG", str(instance_dir / "battery_7step.datasets.json"))
    ).resolve()
    shared_default = data_dir / "shared"
    shared_data_root = Path(
        os.getenv(
            "BATTERY_SITE_DATA_ROOT",
            str(shared_default),
        )
    ).resolve()
    reference_default = data_dir / "reference" / "ListOfreference.xlsx"
    reference_file_path = Path(
        os.getenv(
            "BATTERY_SITE_REFERENCE_FILE",
            str(reference_default if reference_default.exists() else shared_data_root / "ListOfreference.xlsx"),
        )
    ).resolve()
    original_data_root = Path(
        os.getenv("BATTERY_SITE_ORIGINAL_DATA_ROOT", str(data_dir / "original"))
    ).resolve()
    first_optimization_data_root = Path(
        os.getenv("BATTERY_SITE_FIRST_OPTIMIZATION_DATA_ROOT", str(data_dir / "first_optimization"))
    ).resolve()
    first_optimization_diagnostics_root = Path(
        os.getenv(
            "BATTERY_SITE_FIRST_OPTIMIZATION_DIAGNOSTICS_ROOT",
            str(first_optimization_data_root / "diagnostics"),
        )
    ).resolve()
    output_versions_root = Path(
        os.getenv("BATTERY_SITE_OUTPUT_VERSIONS_DIR", str(runtime_paths.output_versions_root))
    ).resolve()
    return BatterySiteConfig(
        root_dir=root_dir,
        package_dir=package_dir,
        instance_dir=instance_dir,
        templates_dir=package_dir / "templates",
        static_dir=package_dir / "static",
        data_dir=data_dir,
        reference_file_path=reference_file_path,
        shared_data_root=shared_data_root,
        original_data_root=original_data_root,
        first_optimization_data_root=first_optimization_data_root,
        first_optimization_diagnostics_root=first_optimization_diagnostics_root,
        dataset_config_path=dataset_config_path,
        output_versions_root=output_versions_root,
        runtime_root=runtime_paths.runtime_root,
        runtime_release_root=runtime_paths.runtime_current_root,
        analyst_password=os.getenv("BATTERY_SITE_ANALYST_PASSWORD", "88888888"),
        strict_startup=_env_flag("BATTERY_SITE_STRICT_STARTUP", default=False),
    )

