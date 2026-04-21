from trade_flow.domain.enums import SupportLevel
from trade_flow.metals.base import MetalAdapter

ADAPTER = MetalAdapter("Li", "lithium", "Lithium", SupportLevel.FULL, ("S1", "S2", "S3", "S4", "S5", "S6", "S7"))
