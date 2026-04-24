from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trade_flow.publishing.refresh_precomputed_from_inputs import refresh_li_co_precomputed_from_inputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the affected Li / Co precomputed snapshots from the existing case inputs JSON files."
    )
    parser.add_argument("--project-root", default=None, help="Project root for the repository.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist regenerated CSV snapshots and refreshed comparison tables.",
    )
    args = parser.parse_args(argv)
    result = refresh_li_co_precomputed_from_inputs(
        project_root=args.project_root,
        write=args.write,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
