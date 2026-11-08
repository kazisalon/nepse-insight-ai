from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas import HealthOut
from app.services.training import get_active_model_run

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        run = get_active_model_run(db)
        database_ok = True
    except Exception:
        run = None
        database_ok = False
    return HealthOut(
        status="ok" if database_ok else "degraded",
        database=database_ok,
        active_model=run.version if run else None,
        environment=get_settings().app_env,
    )
