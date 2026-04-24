from __future__ import annotations

import json
from pathlib import Path

from trade_flow.domain.manifests import RuntimeBundleManifest
from trade_flow.domain.validation import validate_manifest_shape


def validate_runtime_bundle(bundle_root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = bundle_root / "manifest.json"
    catalog_path = bundle_root / "catalog.json"
    if not manifest_path.exists():
        errors.append(f"missing manifest: {manifest_path}")
    if not catalog_path.exists():
        errors.append(f"missing catalog: {catalog_path}")
    if errors:
        return errors
    manifest = RuntimeBundleManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    errors.extend(validate_manifest_shape(manifest))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for key in ("app_data_root", "output_versions_root", "reference_root", "metals_root"):
        if key not in catalog:
            errors.append(f"catalog missing key: {key}")
    return errors
