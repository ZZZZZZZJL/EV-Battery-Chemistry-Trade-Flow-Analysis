from __future__ import annotations

import json
import shutil
from pathlib import Path

from trade_flow.domain.paths import get_runtime_paths
from trade_flow.publishing.release_manifest import build_release_manifest
from trade_flow.utils.hashing import file_sha256


def _copytree_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def build_runtime_bundle(
    *,
    release_root: Path | None = None,
    project_root: Path | None = None,
    data_release_id: str = "data-local-dev-01",
    public_code_commit: str = "working-tree",
    private_pipeline_tag: str = "manual",
) -> Path:
    runtime_paths = get_runtime_paths(project_root=project_root)
    resolved_project_root = runtime_paths.project_root
    target_root = (release_root or (runtime_paths.runtime_releases_root / data_release_id)).resolve()
    app_data_root = target_root / "app_data"
    output_versions_root = target_root / "output_versions"
    reference_root = target_root / "reference"
    metals_root = target_root / "metals"
    target_root.mkdir(parents=True, exist_ok=True)

    _copytree_if_exists(resolved_project_root / "data", app_data_root)
    _copytree_if_exists(resolved_project_root / "output_versions", output_versions_root)
    _copytree_if_exists(resolved_project_root / "data" / "reference", reference_root)
    _copytree_if_exists(resolved_project_root / "data" / "first_optimization" / "optimized", metals_root)

    catalog = {
        "app_data_root": "app_data",
        "output_versions_root": "output_versions",
        "reference_root": "reference",
        "metals_root": "metals",
    }
    manifest = build_release_manifest(
        data_release_id=data_release_id,
        public_code_commit=public_code_commit,
        private_pipeline_tag=private_pipeline_tag,
        algorithms=["baseline", "conversion_factor_optimization", "first_optimization"],
        metals=["Li", "Ni", "Co"],
        years=[2020, 2021, 2022, 2023, 2024],
        hashes={},
    )
    manifest_path = target_root / "manifest.json"
    catalog_path = target_root / "catalog.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    hashes = {
        "manifest.json": file_sha256(manifest_path),
        "catalog.json": file_sha256(catalog_path),
    }
    manifest_with_hashes = build_release_manifest(
        data_release_id=data_release_id,
        public_code_commit=public_code_commit,
        private_pipeline_tag=private_pipeline_tag,
        algorithms=["baseline", "conversion_factor_optimization", "first_optimization"],
        metals=["Li", "Ni", "Co"],
        years=[2020, 2021, 2022, 2023, 2024],
        hashes=hashes,
    )
    manifest_path.write_text(json.dumps(manifest_with_hashes.to_dict(), indent=2), encoding="utf-8")
    return target_root
