from __future__ import annotations

import os
from pathlib import Path


def _configure_bundled_chrome() -> None:
    """Point Kaleido at Chrome downloaded during the Render build."""
    root = Path(__file__).resolve().parent
    path_file = root / ".render" / "chrome_path.txt"
    if path_file.is_file():
        chrome = root / path_file.read_text(encoding="utf-8").strip()
    else:
        chrome = root / ".render" / "chrome" / "chrome-linux64" / "chrome"
    if chrome.is_file():
        os.environ.setdefault("BROWSER_PATH", str(chrome))


_configure_bundled_chrome()

from sankey_web import create_app  # noqa: E402


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)
