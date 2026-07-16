from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sankey_web import create_app
from sankey_web import settings
from sankey_web.generation import active_route
from sankey_web.inventory import inspect_workbook


class InventoryTests(unittest.TestCase):
    def test_inventory_reports_stage_year_and_status_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook = Path(temp_dir) / "source.xlsx"
            pd.DataFrame(
                {
                    "id": [1],
                    "reporterDesc": ["Country A"],
                    "product": ["Total"],
                    "status": ["operating"],
                    2023: [10.0],
                    2024: [12.0],
                }
            ).to_excel(workbook, sheet_name="nickel_mining", index=False)
            inventory = inspect_workbook(workbook, "test", "Test")
            coverage = inventory["coverage"]["Ni"]["mining"]
            self.assertEqual(coverage["years"], [2023, 2024])
            self.assertEqual(coverage["statuses"], ["operating"])

    def test_non_terminal_stage_does_not_require_product_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook = Path(temp_dir) / "scinsight.xlsx"
            pd.DataFrame(
                {
                    "id": [1],
                    "reporterDesc": ["Country A"],
                    "status": ["operating"],
                    2024: [12.0],
                }
            ).to_excel(workbook, sheet_name="lithium_mining", index=False)
            inventory = inspect_workbook(workbook, "scinsight", "SCInsight")
            self.assertIn("mining", inventory["coverage"]["Li"])

    def test_cathode_stage_still_requires_product_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook = Path(temp_dir) / "invalid.xlsx"
            pd.DataFrame(
                {
                    "id": [1],
                    "reporterDesc": ["Country A"],
                    "status": ["operating"],
                    2024: [12.0],
                }
            ).to_excel(workbook, sheet_name="manganese_cathode", index=False)
            with self.assertRaisesRegex(ValueError, "product"):
                inspect_workbook(workbook, "benchmark", "Benchmark")


class RouteTests(unittest.TestCase):
    def test_complete_and_folded_routes_match_the_generator(self) -> None:
        complete = active_route({"showPcam": True, "showBattery": True})
        self.assertEqual(
            [stage["key"] for stage in complete["stages"]],
            ["mining", "processing", "refining", "pcam", "cathode", "battery"],
        )
        folded = active_route(
            {"mergeProcessingRefining": True, "showPcam": False, "showBattery": False}
        )
        self.assertEqual(
            [stage["key"] for stage in folded["stages"]],
            ["mining", "pro_ref", "cathode"],
        )


class WebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_upload_root = settings.UPLOAD_ROOT
        self.original_artifact_root = settings.ARTIFACT_ROOT
        settings.UPLOAD_ROOT = Path(self.temp_dir.name) / "uploads"
        settings.ARTIFACT_ROOT = Path(self.temp_dir.name) / "artifacts"
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        settings.UPLOAD_ROOT = self.original_upload_root
        settings.ARTIFACT_ROOT = self.original_artifact_root
        self.temp_dir.cleanup()

    def workbook_bytes(self, valid: bool = True) -> io.BytesIO:
        buffer = io.BytesIO()
        frame = pd.DataFrame(
            {
                "id": [1],
                "reporterDesc": ["Country A"],
                "product": ["Total"],
                "status": ["operating"],
                2024: [10.0],
            }
            if valid
            else {"id": [1], 2024: [10.0]}
        )
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name="nickel_mining", index=False)
        buffer.seek(0)
        return buffer

    def test_bootstrap_exposes_public_sources_without_authentication(self) -> None:
        response = self.client.get("/api/bootstrap?sessionId=test_session_123")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        sources = {source["key"]: source for source in payload["sources"]}
        self.assertTrue(sources["usgs"]["available"])
        self.assertTrue(sources["ma_2026"]["available"])
        self.assertFalse(sources["scinsight"]["available"])
        self.assertIn("Mn", payload["sources"][0]["metals"])
        self.assertEqual(sources["ma_2026"]["label"], "Ma et al., 2026")
        self.assertGreater(len(payload["countries"]), 100)
        self.assertIn("iso3", payload["countries"][0])

    def test_upload_is_validated_and_scoped_to_session(self) -> None:
        response = self.client.post(
            "/api/uploads/scinsight",
            data={"sessionId": "test_session_123", "file": (self.workbook_bytes(), "source.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        source = next(item for item in response.get_json()["sources"] if item["key"] == "scinsight")
        self.assertTrue(source["available"])
        self.assertIn("mining", source["coverage"]["Ni"])

        other_session = self.client.get("/api/bootstrap?sessionId=other_session_123").get_json()
        other_source = next(item for item in other_session["sources"] if item["key"] == "scinsight")
        self.assertFalse(other_source["available"])

    def test_invalid_upload_returns_a_specific_schema_error(self) -> None:
        response = self.client.post(
            "/api/uploads/benchmark",
            data={"sessionId": "test_session_123", "file": (self.workbook_bytes(False), "bad.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("missing columns", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
