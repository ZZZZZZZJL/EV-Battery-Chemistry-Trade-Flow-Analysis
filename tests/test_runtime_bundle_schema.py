from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from trade_flow.publishing.validate_bundle import validate_runtime_bundle


ROOT = Path(__file__).resolve().parents[1]


class RuntimeBundleSchemaTests(unittest.TestCase):
    def test_schema_files_are_json_readable(self) -> None:
        for name in ("runtime_bundle.schema.json", "manifest.schema.json", "metal_payload.schema.json"):
            payload = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict)

    def test_minimal_bundle_validation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_root = Path(tmp_dir)
            (bundle_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "data_release_id": "data-test",
                        "built_at": "2026-04-20T00:00:00Z",
                        "public_code_commit": "test",
                        "private_pipeline_tag": "manual",
                        "algorithms": ["baseline"],
                        "metals": ["Ni"],
                        "years": [2024],
                        "hashes": {},
                    }
                ),
                encoding="utf-8",
            )
            (bundle_root / "catalog.json").write_text(
                json.dumps(
                    {
                        "app_data_root": "app_data",
                        "output_versions_root": "output_versions",
                        "reference_root": "reference",
                        "metals_root": "metals",
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(validate_runtime_bundle(bundle_root), [])


if __name__ == "__main__":
    unittest.main()
