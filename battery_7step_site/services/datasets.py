from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from battery_7step_site.config import get_battery_site_config


def _default_dataset_config() -> dict[str, Any]:
    site_config = get_battery_site_config()
    shared_root = site_config.shared_data_root
    return {
        "referenceFile": str(site_config.reference_file_path),
        "productionRoot": str(shared_root / "production" / "country"),
        "tradeRoot": str(shared_root / "trade" / "import"),
        "rawImportRoot": str(shared_root / "trade" / "raw_import_by_partner"),
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_dataset_config() -> dict[str, Any]:
    config = _default_dataset_config()
    config_path = get_battery_site_config().dataset_config_path
    if config_path.exists():
        with config_path.open("r", encoding="utf-8-sig") as handle:
            config = _deep_merge(config, json.load(handle))
    return config


def dataset_status(config: dict[str, Any]) -> dict[str, dict[str, str | bool]]:
    reference_path = Path(config["referenceFile"])
    production_root = Path(config["productionRoot"])
    trade_root = Path(config["tradeRoot"])
    return {
        "referenceFile": {
            "label": reference_path.name,
            "exists": reference_path.exists(),
        },
        "productionRoot": {
            "label": production_root.name,
            "exists": production_root.exists(),
        },
        "tradeRoot": {
            "label": trade_root.name,
            "exists": trade_root.exists(),
        },
    }
