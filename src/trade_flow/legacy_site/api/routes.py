"""Legacy compatibility re-exports for the canonical trade_flow web routes."""

from trade_flow.web.api import router
from trade_flow.web.api.bootstrap import bootstrap
from trade_flow.web.api.sankey import FigureRequestModel, figure, figure_get, plotly_asset

__all__ = [
    "FigureRequestModel",
    "bootstrap",
    "figure",
    "figure_get",
    "plotly_asset",
    "router",
]
