from fastapi import APIRouter

from .boards import router as boards_router

router = APIRouter()

# Include boards router under /boards path
router.include_router(boards_router, prefix="/boards", tags=["boards"])
