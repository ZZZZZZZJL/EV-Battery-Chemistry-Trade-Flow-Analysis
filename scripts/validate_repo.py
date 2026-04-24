from __future__ import annotations

from pathlib import Path


REQUIRED_PATHS = [
    Path("apps/web/app.py"),
    Path("src/trade_flow/web/main.py"),
    Path("src/trade_flow/domain/paths.py"),
    Path("src/trade_flow/runtime/bundle_loader.py"),
    Path("src/trade_flow/publishing/build_bundle.py"),
    Path("docs/architecture/repo-layout-and-file-responsibilities.md"),
    Path("docs/runbooks/render-deploy.md"),
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = [str(path) for path in REQUIRED_PATHS if not (root / path).exists()]
    if missing:
        print("Missing required paths:")
        for item in missing:
            print(f" - {item}")
        return 1
    print("Repository layout guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
