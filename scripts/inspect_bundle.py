from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_flow.publishing.validate_bundle import validate_runtime_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_root", type=Path)
    args = parser.parse_args()
    errors = validate_runtime_bundle(args.bundle_root)
    if errors:
        print("Bundle validation failed:")
        for error in errors:
            print(f" - {error}")
        return 1
    manifest = json.loads((args.bundle_root / "manifest.json").read_text(encoding="utf-8"))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
