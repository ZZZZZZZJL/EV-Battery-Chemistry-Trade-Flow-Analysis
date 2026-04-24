from __future__ import annotations

from datetime import UTC, datetime

from trade_flow.domain.manifests import RuntimeBundleManifest


def build_release_manifest(
    *,
    data_release_id: str,
    public_code_commit: str,
    private_pipeline_tag: str,
    algorithms: list[str],
    metals: list[str],
    years: list[int],
    hashes: dict[str, str],
) -> RuntimeBundleManifest:
    return RuntimeBundleManifest(
        data_release_id=data_release_id,
        built_at=datetime.now(UTC).isoformat(),
        public_code_commit=public_code_commit,
        private_pipeline_tag=private_pipeline_tag,
        algorithms=algorithms,
        metals=metals,
        years=years,
        hashes=hashes,
    )
