from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trade_flow.publishing.first_optimization_sync import export_first_optimization_cases


def _resolve_project_root(explicit_root: str | Path | None = None) -> Path:
    if explicit_root is None:
        return PROJECT_ROOT.resolve()
    candidate = Path(explicit_root).resolve()
    return candidate


def _mirror_tree(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return True


def _copy_file(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _copy_matching_files(source_root: Path, destination_root: Path, patterns: tuple[str, ...]) -> list[str]:
    copied: list[str] = []
    if not source_root.exists():
        return copied
    destination_root.mkdir(parents=True, exist_ok=True)
    for pattern in patterns:
        for source in sorted(source_root.glob(pattern)):
            if not source.is_file():
                continue
            shutil.copy2(source, destination_root / source.name)
            copied.append(source.name)
    return copied


def sync_runtime_data_layout(
    *,
    website_root: str | Path | None = None,
    shared_data_root: str | Path | None = None,
    raw_import_root: str | Path | None = None,
    conversion_factor_optimization_root: str | Path | None = None,
    copy_raw_imports: bool = True,
) -> dict[str, Any]:
    project_root = _resolve_project_root(website_root)
    shared_source_root = (
        Path(shared_data_root).resolve()
        if shared_data_root is not None
        else (project_root / "data" / "shared").resolve()
    )
    raw_import_source_root = (
        Path(raw_import_root).resolve()
        if raw_import_root is not None
        else ((project_root / "data" / "shared" / "trade" / "raw_import_by_partner").resolve())
    )
    diagnostics_source_root = (
        Path(conversion_factor_optimization_root).resolve()
        if conversion_factor_optimization_root is not None
        else (project_root / "instance" / "conversion_factor_optimization").resolve()
    )

    data_root = project_root / "data"
    reference_root = data_root / "reference"
    shared_root = data_root / "shared"
    original_root = data_root / "original"
    original_export_root = project_root / "output"
    original_comparison_root = original_export_root / "comparison"

    reference_copied = _copy_file(
        shared_source_root / "ListOfreference.xlsx",
        reference_root / "ListOfreference.xlsx",
    )
    production_copied = _mirror_tree(shared_source_root / "production", shared_root / "production")
    import_trade_copied = _mirror_tree(shared_source_root / "trade" / "import", shared_root / "trade" / "import")

    raw_destination_root = shared_root / "trade" / "raw_import_by_partner"
    raw_destination_root.mkdir(parents=True, exist_ok=True)
    raw_import_copied: list[str] = []
    if copy_raw_imports and raw_import_source_root.exists():
        for source_dir in sorted(raw_import_source_root.glob("UNComtrade_*_Import_ByPartner")):
            if not source_dir.is_dir():
                continue
            shutil.copytree(source_dir, raw_destination_root / source_dir.name, dirs_exist_ok=True)
            raw_import_copied.append(source_dir.name)

    baseline_copied = _mirror_tree(original_export_root / "baseline", original_root / "baseline")
    baseline_comparison_files = _copy_matching_files(
        original_comparison_root,
        original_root / "comparison",
        ("baseline_summary*.csv", "baseline_stage_summary*.csv"),
    )

    first_optimization_result = export_first_optimization_cases(
        website_root=project_root,
        conversion_factor_optimization_root=diagnostics_source_root,
        raw_import_root=raw_destination_root if copy_raw_imports else raw_import_source_root,
    )

    return {
        "project_root": str(project_root),
        "data_root": str(data_root),
        "reference_copied": reference_copied,
        "production_copied": production_copied,
        "import_trade_copied": import_trade_copied,
        "raw_import_copied": raw_import_copied,
        "raw_import_copy_enabled": copy_raw_imports,
        "baseline_copied": baseline_copied,
        "baseline_comparison_files": baseline_comparison_files,
        "first_optimization_sync": first_optimization_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Populate runtime data with shared inputs, Original case files, and First Optimization data."
    )
    parser.add_argument("--website-root", default=None, help="Project root for the consolidated repository.")
    parser.add_argument("--shared-data-root", default=None, help="Source root containing ListOfreference.xlsx, production, and trade.")
    parser.add_argument("--raw-import-root", default=None, help="Source root containing UNComtrade_*_Import_ByPartner folders.")
    parser.add_argument(
        "--conversion-factor-optimization-root",
        default=None,
        help="Source conversion_factor_optimization workspace root.",
    )
    parser.add_argument("--skip-raw-import-copy", action="store_true", help="Do not mirror raw import folders into data/shared during this run.")
    args = parser.parse_args(argv)
    result = sync_runtime_data_layout(
        website_root=args.website_root,
        shared_data_root=args.shared_data_root,
        raw_import_root=args.raw_import_root,
        conversion_factor_optimization_root=args.conversion_factor_optimization_root,
        copy_raw_imports=not args.skip_raw_import_copy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
