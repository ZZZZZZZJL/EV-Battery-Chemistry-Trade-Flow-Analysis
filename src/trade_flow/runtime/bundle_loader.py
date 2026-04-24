from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trade_flow.domain.manifests import RuntimeBundleManifest
from trade_flow.domain.paths import RuntimePaths, get_runtime_paths
from trade_flow.domain.validation import require_existing_dir, validate_manifest_shape


@dataclass(frozen=True)
class RuntimeBundleDescriptor:
    bundle_root: Path
    manifest: RuntimeBundleManifest
    catalog: dict


def load_bundle_descriptor(paths: RuntimePaths | None = None, *, strict: bool = True) -> RuntimeBundleDescriptor:
    runtime_paths = paths or get_runtime_paths()
    bundle_root = runtime_paths.runtime_current_root
    if strict:
        require_existing_dir(bundle_root, "runtime current root")
    manifest_path = bundle_root / "manifest.json"
    catalog_path = bundle_root / "catalog.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"runtime manifest is missing: {manifest_path}")
    if not catalog_path.exists():
        raise FileNotFoundError(f"runtime catalog is missing: {catalog_path}")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    manifest = RuntimeBundleManifest.from_dict(manifest_payload)
    errors = validate_manifest_shape(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    return RuntimeBundleDescriptor(bundle_root=bundle_root, manifest=manifest, catalog=catalog_payload)
