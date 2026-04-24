from __future__ import annotations

from pathlib import Path

from .manifests import RuntimeBundleManifest


def require_existing_dir(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} is missing: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} must be a directory: {path}")
    return path


def validate_manifest_shape(manifest: RuntimeBundleManifest) -> list[str]:
    errors: list[str] = []
    if not manifest.data_release_id:
        errors.append("manifest.data_release_id is required")
    if not manifest.built_at:
        errors.append("manifest.built_at is required")
    if not manifest.public_code_commit:
        errors.append("manifest.public_code_commit is required")
    if not manifest.private_pipeline_tag:
        errors.append("manifest.private_pipeline_tag is required")
    return errors

