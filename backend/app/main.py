import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nepse_insight")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
        logger.info("Database schema ready")
    except Exception as error:
        logger.error("Database initialisation failed: %s", error)
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Research and decision-support API for the Nepal Stock Exchange. "
        "Produces explainable BUY, SELL, HOLD and NO TRADE insights. It does not place orders."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "api": settings.api_prefix}
