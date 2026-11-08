from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ModelRun
from app.schemas import ModelRunOut, ModelRunSummary, TrainRequest
from app.services.training import TrainingError, get_active_model_run, set_active_model, train_model

router = APIRouter(prefix="/models", tags=["models"])


@router.post("/train", response_model=ModelRunOut, status_code=status.HTTP_201_CREATED)
def train(payload: TrainRequest, db: Session = Depends(get_db)) -> ModelRun:
    settings = get_settings()
    try:
        return train_model(
            db,
            horizon=payload.horizon_days or settings.default_horizon_days,
            threshold=payload.return_threshold or settings.default_return_threshold,
            validation_fraction=payload.validation_fraction,
            params=payload.params,
            activate=payload.activate,
        )
    except TrainingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error


@router.get("", response_model=list[ModelRunSummary])
def list_models(db: Session = Depends(get_db)) -> list[ModelRun]:
    return list(db.scalars(select(ModelRun).order_by(ModelRun.created_at.desc())))


@router.get("/active", response_model=ModelRunOut)
def active_model(db: Session = Depends(get_db)) -> ModelRun:
    run = get_active_model_run(db)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active model")
    return run


@router.get("/{model_id}", response_model=ModelRunOut)
def read_model(model_id: int, db: Session = Depends(get_db)) -> ModelRun:
    run = db.get(ModelRun, model_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    return run


@router.post("/{model_id}/activate", response_model=ModelRunSummary)
def activate_model(model_id: int, db: Session = Depends(get_db)) -> ModelRun:
    run = db.get(ModelRun, model_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    set_active_model(db, model_id)
    db.commit()
    db.refresh(run)
    return run
