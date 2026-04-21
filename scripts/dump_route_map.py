from __future__ import annotations

from apps.web.app import app


def main() -> int:
    for route in app.routes:
        methods = ",".join(sorted(route.methods or []))
        print(f"{methods:20} {route.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
