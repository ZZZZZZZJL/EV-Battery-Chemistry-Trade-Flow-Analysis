from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
        cwd=ROOT,
        check=True,
    )

    from plotly.io import get_chrome

    chrome_dir = ROOT / ".render" / "chrome"
    chrome_dir.mkdir(parents=True, exist_ok=True)
    chrome_path = Path(get_chrome(chrome_dir)).resolve()
    if not chrome_path.is_file():
        raise FileNotFoundError(f"Plotly did not create the Chrome executable: {chrome_path}")

    relative_path = chrome_path.relative_to(ROOT)
    path_file = ROOT / ".render" / "chrome_path.txt"
    path_file.write_text(relative_path.as_posix(), encoding="utf-8")
    os.environ["BROWSER_PATH"] = str(chrome_path)

    from verify_render_png import main as verify_png

    verify_png()


if __name__ == "__main__":
    main()
