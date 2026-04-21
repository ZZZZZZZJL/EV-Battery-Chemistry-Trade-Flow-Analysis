from __future__ import annotations

import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn

from apps.web.app import app


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fetch(url: str) -> tuple[int, str]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.getcode(), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _wait_for_server(url: str, timeout_seconds: float = 30.0) -> tuple[int, str]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return _fetch(url)
        except URLError as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for local server at {url}: {last_error}")


def main() -> int:
    port = _reserve_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        health_status, _ = _wait_for_server(f"http://127.0.0.1:{port}/healthz")
        bootstrap_status, _ = _fetch(f"http://127.0.0.1:{port}/api/bootstrap")
        print(f"/healthz -> {health_status}")
        print(f"/api/bootstrap -> {bootstrap_status}")
        return 0 if health_status == 200 and bootstrap_status == 200 else 1
    finally:
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
