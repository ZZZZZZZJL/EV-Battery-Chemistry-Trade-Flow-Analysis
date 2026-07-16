from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

from pipeline import run_pipeline, settings_from_module


def _load_config(path: Path) -> ModuleType:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Configuration file does not exist: {resolved}")
    spec = importlib.util.spec_from_file_location("standalone_custom_sankey_user_config", resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load configuration file: {resolved}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate standalone production/trade Sankey PNG, HTML, and audit tables."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.py",
        help="Python configuration file. Defaults to config.py beside this script.",
    )
    args = parser.parse_args()
    settings = settings_from_module(_load_config(args.config))
    outputs = run_pipeline(settings)
    print("Standalone Sankey generation completed.")
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
