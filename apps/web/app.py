"""Canonical ASGI entrypoint for the web product.

The existing battery_7step_site package remains available as a compatibility
layer while the repository transitions to the monorepo layout.
"""

from battery_7step_site.main import app

__all__ = ["app"]
