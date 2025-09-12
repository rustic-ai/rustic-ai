from fastapi import APIRouter

from .boards import boards_router

addons_router = APIRouter()

addons_router.include_router(boards_router, prefix="/boards", tags=["boards"])
