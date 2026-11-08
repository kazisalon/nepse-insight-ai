from fastapi import APIRouter

from app.api import companies, models, signals, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(companies.router)
api_router.include_router(models.router)
api_router.include_router(signals.router)
