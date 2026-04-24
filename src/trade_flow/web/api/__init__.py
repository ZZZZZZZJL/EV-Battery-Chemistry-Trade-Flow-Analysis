from fastapi import APIRouter

from .bootstrap import router as bootstrap_router
from .sankey import router as sankey_router
from .tables import router as tables_router


router = APIRouter()
router.include_router(bootstrap_router)
router.include_router(sankey_router)
router.include_router(tables_router)

__all__ = ["router"]
