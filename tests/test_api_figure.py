from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from trade_flow.web.api import sankey


def fake_repo(root: Path, *, metals: list[str] | None = None, years: list[int] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        metals=metals or ["Ni"],
        years=years or [2024],
        original_data_root=root,
        first_optimization_data_root=root,
        first_optimization_diagnostics_root=root,
        version_output_root=root,
    )


class ApiFigureTests(unittest.TestCase):
    def setUp(self) -> None:
        sankey._build_cached_payload.cache_clear()

    def test_invalid_metal_returns_400(self) -> None:
        with TemporaryDirectory() as tmp:
            request = sankey.FigureRequestModel(year=2024, metal="Cu")
            with patch("trade_flow.web.api.sankey.get_repository", return_value=fake_repo(Path(tmp))):
                with self.assertRaises(HTTPException) as context:
                    sankey.figure(request)
            self.assertEqual(context.exception.status_code, 400)

    def test_wrong_analyst_password_does_not_touch_runtime(self) -> None:
        request = sankey.FigureRequestModel(
            year=2024,
            metal="Ni",
            accessMode="analyst",
            accessPassword="wrong-password",
        )
        with patch("trade_flow.web.api.sankey.get_repository") as mock_get_repository:
            with self.assertRaises(HTTPException) as context:
                sankey.figure(request)
        self.assertEqual(context.exception.status_code, 403)
        mock_get_repository.assert_not_called()

    def test_runtime_missing_error_is_sanitized(self) -> None:
        request = sankey.FigureRequestModel(year=2024, metal="Ni")
        private_path = r"E:\private\runtime\secret.csv"
        with patch("trade_flow.web.api.sankey.get_repository", side_effect=FileNotFoundError(private_path)):
            with self.assertRaises(HTTPException) as context:
                sankey.figure(request)
        self.assertEqual(context.exception.status_code, 503)
        self.assertNotIn("E:\\", str(context.exception.detail))
        self.assertNotIn("secret.csv", str(context.exception.detail))

    def test_figure_payload_cache_uses_runtime_version(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = fake_repo(Path(tmp))
            request = sankey.FigureRequestModel(year=2024, metal="Ni")
            with (
                patch("trade_flow.web.api.sankey.get_repository", return_value=repo),
                patch("trade_flow.web.api.sankey.build_sankey_payload", return_value={"figure": {"data": [], "layout": {}}}) as mock_build,
            ):
                sankey.figure(request)
                sankey.figure(request)
        self.assertEqual(mock_build.call_count, 1)

    def test_runtime_version_changes_with_manifest_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = sankey._runtime_cache_version(fake_repo(root, metals=["Ni"], years=[2024]))
            second = sankey._runtime_cache_version(fake_repo(root, metals=["Ni", "Li"], years=[2024]))
        self.assertNotEqual(first, second)

    def test_public_request_cache_key_excludes_password(self) -> None:
        request = sankey.FigureRequestModel(
            year=2024,
            metal="Ni",
            accessPassword="never-cache-this",
        )
        request_json = sankey._public_request_json(request, "guest")
        self.assertNotIn("never-cache-this", request_json)


if __name__ == "__main__":
    unittest.main()
