from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
    dataset_config_path: Path
    output_dir: Path
    output_versions_root: Path
    analyst_password: str
    strict_startup: bool


def get_battery_site_config() -> BatterySiteConfig:
    root_dir = Path(__file__).resolve().parent.parent
    package_dir = root_dir / "battery_7step_site"
    instance_dir = Path(os.getenv("BATTERY_SITE_INSTANCE_DIR", str(root_dir / "instance"))).resolve()
    instance_dir.mkdir(parents=True, exist_ok=True)
    dataset_config_path = Path(
        os.getenv("BATTERY_SITE_DATASET_CONFIG", str(instance_dir / "battery_7step.datasets.json"))
    ).resolve()
    output_dir = Path(os.getenv("BATTERY_SITE_OUTPUT_DIR", str(root_dir / "output"))).resolve()
    output_versions_root = Path(
        os.getenv("BATTERY_SITE_OUTPUT_VERSIONS_DIR", str(root_dir / "output_versions"))
    ).resolve()
    return BatterySiteConfig(
        root_dir=root_dir,
        package_dir=package_dir,
        instance_dir=instance_dir,
        templates_dir=package_dir / "templates",
        static_dir=package_dir / "static",
        dataset_config_path=dataset_config_path,
        output_dir=output_dir,
        output_versions_root=output_versions_root,
        analyst_password=os.getenv("BATTERY_SITE_ANALYST_PASSWORD", "88888888"),
        strict_startup=_env_flag("BATTERY_SITE_STRICT_STARTUP", default=False),
    )
