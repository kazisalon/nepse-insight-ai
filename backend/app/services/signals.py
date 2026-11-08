from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
import xgboost as xgb
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Company, ModelRun, Signal
from app.services.features import FEATURE_LABELS, build_feature_frame
from app.services.training import TrainingError, get_active_model_run, load_classifier

BUY, SELL, HOLD, NO_TRADE = "BUY", "SELL", "HOLD", "NO TRADE"


@dataclass
class Insight:
    symbol: str
    signal_date: date
    close: float
    action: str
    confidence: float
    prob_up: float
    prob_neutral: float
    prob_down: float
    reasons: list[str] = field(default_factory=list)
    drivers: list[dict] = field(default_factory=list)
    indicators: dict = field(default_factory=dict)


def _technical_reasons(row: pd.Series) -> list[str]:
    reasons = []
    rsi = row.get("rsi_14")
    if pd.notna(rsi):
        if rsi < 30:
            reasons.append(f"RSI at {rsi:.1f} indicates oversold conditions")
        elif rsi > 70:
            reasons.append(f"RSI at {rsi:.1f} indicates overbought conditions")
    trend = row.get("close_vs_sma_50")
    if pd.notna(trend):
        side = "above" if trend >= 0 else "below"
        reasons.append(f"Price is {abs(trend) * 100:.1f}% {side} its 50-day average")
    hist = row.get("macd_hist")
    if pd.notna(hist):
        reasons.append("MACD momentum is positive" if hist > 0 else "MACD momentum is negative")
    volume = row.get("volume_ratio_20")
    if pd.notna(volume) and volume >= 1.5:
        reasons.append(f"Volume is {volume:.1f}x its 20-day average")
    strength = row.get("relative_strength_20")
    if pd.notna(strength) and abs(strength) >= 0.03:
        verb = "outperformed" if strength > 0 else "underperformed"
        reasons.append(f"Stock has {verb} the market by {abs(strength) * 100:.1f}% over 20 days")
    return reasons


def _drivers(contributions: np.ndarray, row: pd.Series, feature_names: list[str], limit: int = 6) -> list[dict]:
    order = np.argsort(-np.abs(contributions))[:limit]
    return [
        {
            "feature": feature_names[index],
            "label": FEATURE_LABELS.get(feature_names[index], feature_names[index]),
            "value": None if pd.isna(row[feature_names[index]]) else round(float(row[feature_names[index]]), 6),
            "contribution": round(float(contributions[index]), 6),
            "effect": "supports" if contributions[index] > 0 else "opposes",
        }
        for index in order
        if abs(contributions[index]) > 1e-6
    ]


def _decide(row: pd.Series, probabilities: np.ndarray, market_date: pd.Timestamp) -> tuple[str, list[str]]:
    settings = get_settings()
    prob_down, prob_neutral, prob_up = (float(value) for value in probabilities)
    guards = []
    if row["history_days"] < settings.min_history_days:
        guards.append(f"Only {int(row['history_days'])} trading days of history available")
    turnover = row.get("avg_turnover_20")
    if pd.isna(turnover) or turnover < settings.min_avg_turnover:
        guards.append("Average daily turnover is below the liquidity threshold")
    if (market_date - row["trade_date"]).days > settings.max_data_staleness_days:
        guards.append(f"Latest price is stale ({row['trade_date'].date().isoformat()})")
    if max(prob_down, prob_neutral, prob_up) < settings.min_confidence:
        guards.append("Model confidence is too low to act on")
    if guards:
        return NO_TRADE, guards

    if prob_up >= settings.buy_probability and prob_up - prob_down >= settings.min_edge:
        return BUY, [f"Model estimates a {prob_up * 100:.0f}% chance of an upside move"]
    if prob_down >= settings.sell_probability and prob_down - prob_up >= settings.min_edge:
        return SELL, [f"Model estimates a {prob_down * 100:.0f}% chance of a downside move"]
    return HOLD, ["No clear directional edge between upside and downside scenarios"]


def _require_model(db: Session) -> ModelRun:
    run = get_active_model_run(db)
    if run is None:
        raise TrainingError("No active model. Train a model first.")
    return run


def generate_insights(db: Session, symbols: list[str] | None = None, as_of: date | None = None) -> tuple[ModelRun, list[Insight]]:
    run = _require_model(db)
    model = load_classifier(run.artifact_path)
    frame = build_feature_frame(db)
    if frame.empty:
        return run, []
    if as_of:
        frame = frame[frame["trade_date"] <= pd.Timestamp(as_of)]
    market_date = frame["trade_date"].max()
    if symbols:
        frame = frame[frame["symbol"].isin([symbol.upper() for symbol in symbols])]
    latest = frame.groupby("symbol").tail(1).reset_index(drop=True)
    if latest.empty:
        return run, []

    features = latest[run.feature_names]
    probabilities = model.predict_proba(features)
    contributions = model.get_booster().predict(xgb.DMatrix(features), pred_contribs=True)

    insights = []
    for index, row in latest.iterrows():
        action, decision_reasons = _decide(row, probabilities[index], market_date)
        focus_class = {BUY: 2, SELL: 0}.get(action, int(probabilities[index].argmax()))
        insights.append(
            Insight(
                symbol=row["symbol"],
                signal_date=row["trade_date"].date(),
                close=float(row["close"]),
                action=action,
                confidence=round(float(probabilities[index].max()), 4),
                prob_down=round(float(probabilities[index][0]), 4),
                prob_neutral=round(float(probabilities[index][1]), 4),
                prob_up=round(float(probabilities[index][2]), 4),
                reasons=decision_reasons + _technical_reasons(row),
                drivers=_drivers(contributions[index, focus_class, :-1], row, run.feature_names),
                indicators={
                    key: None if pd.isna(row[key]) else round(float(row[key]), 6)
                    for key in ("rsi_14", "macd_hist", "close_vs_sma_50", "volume_ratio_20", "volatility_20", "avg_turnover_20")
                },
            )
        )
    return run, insights


def persist_insights(db: Session, run: ModelRun, insights: list[Insight]) -> int:
    if not insights:
        return 0
    company_ids = dict(db.execute(select(Company.symbol, Company.id)).all())
    records = [
        {
            "company_id": company_ids[insight.symbol],
            "model_run_id": run.id,
            "signal_date": insight.signal_date,
            "action": insight.action,
            "confidence": insight.confidence,
            "prob_up": insight.prob_up,
            "prob_neutral": insight.prob_neutral,
            "prob_down": insight.prob_down,
            "close": insight.close,
            "reasons": insight.reasons,
            "drivers": insight.drivers,
        }
        for insight in insights
    ]
    statement = insert(Signal).values(records)
    statement = statement.on_conflict_do_update(
        constraint="uq_signal_company_model_date",
        set_={
            key: statement.excluded[key]
            for key in ("action", "confidence", "prob_up", "prob_neutral", "prob_down", "close", "reasons", "drivers")
        },
    )
    db.execute(statement)
    db.commit()
    return len(records)


def latest_signals(db: Session, action: str | None = None, limit: int = 100) -> list[Signal]:
    run = _require_model(db)
    latest_per_company = (
        select(Signal.company_id, func.max(Signal.signal_date).label("signal_date"))
        .where(Signal.model_run_id == run.id)
        .group_by(Signal.company_id)
        .subquery()
    )
    query = (
        select(Signal)
        .join(
            latest_per_company,
            (Signal.company_id == latest_per_company.c.company_id)
            & (Signal.signal_date == latest_per_company.c.signal_date),
        )
        .where(Signal.model_run_id == run.id)
        .order_by(Signal.confidence.desc())
        .limit(limit)
    )
    if action:
        query = query.where(Signal.action == action.upper())
    return list(db.scalars(query))
