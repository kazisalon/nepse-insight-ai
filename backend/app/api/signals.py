from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import Action, GenerateResult, InsightOut, SignalOut
from app.services.signals import generate_insights, latest_signals, persist_insights
from app.services.training import TrainingError

router = APIRouter(tags=["insights"])


def _model_error(error: TrainingError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.post("/signals/generate", response_model=GenerateResult)
def generate(as_of: date | None = None, db: Session = Depends(get_db)) -> GenerateResult:
    try:
        run, insights = generate_insights(db, as_of=as_of)
    except TrainingError as error:
        raise _model_error(error) from error
    persist_insights(db, run, insights)
    return GenerateResult(
        model_version=run.version,
        generated=len(insights),
        summary=dict(Counter(insight.action for insight in insights)),
    )


@router.get("/signals", response_model=list[SignalOut])
def list_signals(
    action: Action | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[SignalOut]:
    try:
        signals = latest_signals(db, action=action, limit=limit)
    except TrainingError as error:
        raise _model_error(error) from error
    return [
        SignalOut(
            symbol=signal.company.symbol,
            signal_date=signal.signal_date,
            close=signal.close,
            action=signal.action,
            confidence=signal.confidence,
            prob_up=signal.prob_up,
            prob_neutral=signal.prob_neutral,
            prob_down=signal.prob_down,
            reasons=signal.reasons,
            drivers=signal.drivers,
            model_version=signal.model_run.version,
        )
        for signal in signals
    ]


@router.get("/companies/{symbol}/insight", response_model=InsightOut)
def company_insight(symbol: str, as_of: date | None = None, db: Session = Depends(get_db)) -> InsightOut:
    try:
        run, insights = generate_insights(db, symbols=[symbol], as_of=as_of)
    except TrainingError as error:
        raise _model_error(error) from error
    if not insights:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No price data for {symbol.upper()}")
    insight = insights[0]
    return InsightOut(**insight.__dict__, model_version=run.version, horizon_days=run.horizon_days)
