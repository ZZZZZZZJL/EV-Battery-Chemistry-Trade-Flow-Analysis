from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from trade_flow.legacy_site.services.precomputed_repository import _resolve_selected_workbook_path


class SelectedWorkbookPathTests(unittest.TestCase):
    def test_resolves_workbook_path_after_workspace_move(self) -> None:
        current_project = Path("E:/new/website/worktrees/repo")
        workbook = Path("E:/new/website/worktrees/conversion_factor_hyperparameter_search/report.xlsx")
        stale_path = Path("E:/old/website/worktrees/conversion_factor_hyperparameter_search/report.xlsx")

        def exists(path: Path) -> bool:
            return path == workbook

        with patch.object(Path, "exists", exists):
            resolved = _resolve_selected_workbook_path(stale_path, current_project)

        self.assertEqual(resolved, workbook)


if __name__ == "__main__":
    unittest.main()
