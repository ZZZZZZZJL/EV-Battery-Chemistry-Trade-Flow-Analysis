"""Legacy compatibility wrapper around the canonical trade_flow web app."""

from trade_flow.web.main import app, healthz

__all__ = ["app", "healthz"]
