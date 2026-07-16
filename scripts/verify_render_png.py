from __future__ import annotations

import os
import tempfile
from pathlib import Path

import plotly.graph_objects as go


def main() -> None:
    browser_path = Path(os.environ.get("BROWSER_PATH", ""))
    if not browser_path.is_file():
        raise FileNotFoundError(f"Render Chrome executable was not created: {browser_path}")

    output_path = Path(tempfile.gettempdir()) / "render-kaleido-smoke.png"
    figure = go.Figure(go.Scatter(x=[0, 1], y=[0, 1]))
    figure.write_image(output_path, format="png", width=320, height=200, scale=1)
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Kaleido smoke test did not create a PNG: {output_path}")
    print(f"Kaleido PNG smoke test passed with {browser_path}")


if __name__ == "__main__":
    main()
