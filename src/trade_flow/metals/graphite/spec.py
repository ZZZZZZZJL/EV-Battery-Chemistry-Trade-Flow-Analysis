from trade_flow.domain.enums import SupportLevel
from trade_flow.metals.base import MetalAdapter

ADAPTER = MetalAdapter("Graphite", "graphite", "Graphite", SupportLevel.PARTIAL, ("S1", "S2", "S3"), "Skeleton only")
