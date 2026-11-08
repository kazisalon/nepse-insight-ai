from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)
from sklearn.utils.class_weight import compute_sample_weight
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

from app.config import get_settings
from app.models import ModelRun
from app.services.features import CLASS_LABELS, FEATURE_COLUMNS, add_targets, build_feature_frame

DEFAULT_PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.03,
    "max_depth": 4,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "gamma": 0.0,
}

MIN_TRAINING_ROWS = 300


class TrainingError(ValueError):
    pass


@dataclass
class DatasetSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp


def time_split(frame: pd.DataFrame, horizon: int, validation_fraction: float) -> DatasetSplit:
    dates = np.sort(frame["trade_date"].unique())
    cut = int(len(dates) * (1 - validation_fraction))
    if cut - horizon < 20 or len(dates) - cut < 10:
        raise TrainingError("Not enough trading days to create a leakage-free train/validation split")
    train_dates = dates[: cut - horizon]
    validation_dates = dates[cut:]
    return DatasetSplit(
        train=frame[frame["trade_date"].isin(train_dates)],
        validation=frame[frame["trade_date"].isin(validation_dates)],
        train_start=pd.Timestamp(train_dates[0]),
        train_end=pd.Timestamp(train_dates[-1]),
        validation_start=pd.Timestamp(validation_dates[0]),
    )


def _signal_metrics(validation: pd.DataFrame, probabilities: np.ndarray) -> dict:
    settings = get_settings()
    prob_down, prob_up = probabilities[:, 0], probabilities[:, 2]
    buy_mask = (prob_up >= settings.buy_probability) & (prob_up - prob_down >= settings.min_edge)
    sell_mask = (prob_down >= settings.sell_probability) & (prob_down - prob_up >= settings.min_edge)
    forward = validation["forward_return"].to_numpy()

    def summarise(mask: np.ndarray, positive: np.ndarray) -> dict:
        count = int(mask.sum())
        return {
            "count": count,
            "hit_rate": float(positive[mask].mean()) if count else None,
            "avg_forward_return": float(forward[mask].mean()) if count else None,
        }

    return {
        "buy": summarise(buy_mask, forward > 0),
        "sell": summarise(sell_mask, forward < 0),
        "baseline_avg_forward_return": float(forward.mean()),
    }


def _evaluate(validation: pd.DataFrame, probabilities: np.ndarray) -> dict:
    actual = validation["target"].to_numpy()
    predicted = probabilities.argmax(axis=1)
    precision, recall, f1, support = precision_recall_fscore_support(
        actual, predicted, labels=[0, 1, 2], zero_division=0
    )
    majority = np.bincount(actual, minlength=3).argmax()
    return {
        "accuracy": float(accuracy_score(actual, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, average="macro", zero_division=0)),
        "log_loss": float(log_loss(actual, probabilities, labels=[0, 1, 2])),
        "majority_baseline_accuracy": float((actual == majority).mean()),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(CLASS_LABELS)
        },
        "confusion_matrix": confusion_matrix(actual, predicted, labels=[0, 1, 2]).tolist(),
        "signals": _signal_metrics(validation, probabilities),
    }


def train_model(
    db: Session,
    horizon: int,
    threshold: float,
    validation_fraction: float = 0.2,
    params: dict | None = None,
    activate: bool = True,
) -> ModelRun:
    settings = get_settings()
    frame = build_feature_frame(db)
    if frame.empty:
        raise TrainingError("No price data available. Import prices before training.")

    frame = add_targets(frame, horizon, threshold)
    frame = frame[(frame["target"] >= 0) & (frame["history_days"] >= settings.min_history_days)]
    if len(frame) < MIN_TRAINING_ROWS:
        raise TrainingError(f"Need at least {MIN_TRAINING_ROWS} labelled rows, found {len(frame)}")

    split = time_split(frame, horizon, validation_fraction)
    if split.train["target"].nunique() < 3:
        raise TrainingError("Training data does not contain all three outcome classes. Adjust the threshold.")

    model_params = {**DEFAULT_PARAMS, **(params or {})}
    model = XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        tree_method="hist",
        early_stopping_rounds=50,
        random_state=42,
        n_jobs=-1,
        **model_params,
    )
    model.fit(
        split.train[FEATURE_COLUMNS],
        split.train["target"],
        sample_weight=compute_sample_weight("balanced", split.train["target"]),
        eval_set=[(split.validation[FEATURE_COLUMNS], split.validation["target"])],
        verbose=False,
    )

    probabilities = model.predict_proba(split.validation[FEATURE_COLUMNS])
    metrics = _evaluate(split.validation, probabilities)
    metrics.update(
        {
            "best_iteration": int(model.best_iteration),
            "train_rows": int(len(split.train)),
            "validation_rows": int(len(split.validation)),
            "validation_start": split.validation_start.date().isoformat(),
            "symbols": int(frame["symbol"].nunique()),
            "class_distribution": {
                label: int(count)
                for label, count in zip(CLASS_LABELS, np.bincount(frame["target"], minlength=3))
            },
        }
    )

    gains = model.get_booster().get_score(importance_type="gain")
    total_gain = sum(gains.values()) or 1.0
    importance = dict(
        sorted(((name, round(gains.get(name, 0.0) / total_gain, 6)) for name in FEATURE_COLUMNS), key=lambda item: -item[1])
    )

    version = datetime.now(timezone.utc).strftime("xgb-%Y%m%d-%H%M%S")
    settings.model_path.mkdir(parents=True, exist_ok=True)
    artifact = settings.model_path / f"{version}.json"
    model.save_model(artifact)

    run = ModelRun(
        version=version,
        horizon_days=horizon,
        return_threshold=threshold,
        params=model_params,
        metrics=metrics,
        feature_names=FEATURE_COLUMNS,
        feature_importance=importance,
        train_start=split.train_start.date(),
        train_end=split.train_end.date(),
        n_samples=int(len(frame)),
        artifact_path=str(artifact),
        is_active=False,
    )
    db.add(run)
    db.flush()
    if activate:
        set_active_model(db, run.id)
    db.commit()
    db.refresh(run)
    return run


def set_active_model(db: Session, model_run_id: int) -> None:
    db.execute(update(ModelRun).values(is_active=False))
    db.execute(update(ModelRun).where(ModelRun.id == model_run_id).values(is_active=True))


def get_active_model_run(db: Session) -> ModelRun | None:
    return db.scalar(select(ModelRun).where(ModelRun.is_active.is_(True)))


@lru_cache(maxsize=4)
def load_classifier(artifact_path: str) -> XGBClassifier:
    if not Path(artifact_path).exists():
        raise TrainingError(f"Model artifact not found: {artifact_path}")
    model = XGBClassifier()
    model.load_model(artifact_path)
    return model
