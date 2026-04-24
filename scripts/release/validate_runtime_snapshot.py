from __future__ import annotations

import json

from trade_flow.runtime.runtime_checks import gather_runtime_status


def main() -> int:
    status = gather_runtime_status()
    print(json.dumps(status.to_public_dict(), indent=2))
    return 0 if status.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
