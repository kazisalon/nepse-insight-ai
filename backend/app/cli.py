import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.services.ingestion import ensure_companies, parse_price_csv, upsert_prices
from app.services.signals import generate_insights, persist_insights
from app.services.training import train_model

DEMO_COMPANIES = {
    "NABIL": ("Nabil Bank Limited", "Commercial Banks"),
    "NICA": ("NIC Asia Bank Limited", "Commercial Banks"),
    "GBIME": ("Global IME Bank Limited", "Commercial Banks"),
    "EBL": ("Everest Bank Limited", "Commercial Banks"),
    "NTC": ("Nepal Doorsanchar Company Limited", "Others"),
    "HDL": ("Himalayan Distillery Limited", "Manufacturing And Processing"),
    "UPPER": ("Upper Tamakoshi Hydropower Limited", "Hydro Power"),
    "CHCL": ("Chilime Hydropower Company Limited", "Hydro Power"),
    "SHL": ("Soaltee Hotel Limited", "Hotels And Tourism"),
    "NRIC": ("Nepal Reinsurance Company Limited", "Life Insurance"),
}


def nepse_trading_days(start: date, end: date) -> list[date]:
    days, cursor = [], start
    while cursor <= end:
        if cursor.weekday() not in (4, 5):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def synthetic_prices(years: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = date.today()
    days = nepse_trading_days(end - timedelta(days=365 * years), end)
    market = rng.normal(0.0002, 0.009, len(days))
    frames = []
    for symbol in DEMO_COMPANIES:
        beta = rng.uniform(0.6, 1.4)
        noise = rng.normal(0, rng.uniform(0.010, 0.020), len(days))
        momentum = np.zeros(len(days))
        returns = np.zeros(len(days))
        for index in range(1, len(days)):
            momentum[index] = 0.96 * momentum[index - 1] + rng.normal(0, 0.0025)
            returns[index] = beta * market[index] + momentum[index] + noise[index]
        returns = np.clip(returns, -0.10, 0.10)
        close = rng.uniform(250, 1500) * np.exp(np.cumsum(returns))
        spread = np.abs(rng.normal(0, 0.008, len(days)))
        open_ = close * (1 + rng.normal(0, 0.004, len(days)))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.lognormal(10, 0.5, len(days)) * (1 + 25 * np.abs(returns))
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "trade_date": days,
                    "open": open_.round(2),
                    "high": high.round(2),
                    "low": low.round(2),
                    "close": close.round(2),
                    "volume": volume.round(0),
                    "turnover": (volume * close).round(2),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def command_init_db(_: argparse.Namespace) -> None:
    init_db()
    print("Database schema created")


def command_import(args: argparse.Namespace) -> None:
    frame = parse_price_csv(Path(args.path).read_bytes(), args.symbol.upper() if args.symbol else None)
    with SessionLocal() as db:
        rows = upsert_prices(db, frame, source=args.source)
    print(f"Imported {rows} rows for {frame['symbol'].nunique()} symbols")


def command_seed_demo(args: argparse.Namespace) -> None:
    init_db()
    frame = synthetic_prices(args.years, args.seed)
    with SessionLocal() as db:
        ensure_companies(
            db,
            list(DEMO_COMPANIES),
            {symbol: {"name": name, "sector": sector} for symbol, (name, sector) in DEMO_COMPANIES.items()},
        )
        db.commit()
        rows = upsert_prices(db, frame, source="synthetic")
    print(f"Seeded {rows} synthetic price rows for {len(DEMO_COMPANIES)} symbols (source=synthetic)")


def command_train(args: argparse.Namespace) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        run = train_model(
            db,
            horizon=args.horizon or settings.default_horizon_days,
            threshold=args.threshold or settings.default_return_threshold,
        )
    metrics = {key: run.metrics[key] for key in ("accuracy", "balanced_accuracy", "macro_f1", "log_loss", "majority_baseline_accuracy")}
    print(f"Trained {run.version} on {run.n_samples} rows")
    print(json.dumps(metrics, indent=2))


def command_generate(_: argparse.Namespace) -> None:
    with SessionLocal() as db:
        run, insights = generate_insights(db)
        persist_insights(db, run, insights)
    print(f"Generated {len(insights)} signals with {run.version}: {dict(Counter(item.action for item in insights))}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="NEPSE Insight AI management commands")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init-db", help="Create database tables").set_defaults(handler=command_init_db)

    importer = commands.add_parser("import-csv", help="Import OHLCV prices from a CSV file")
    importer.add_argument("path")
    importer.add_argument("--symbol", help="Symbol to use when the CSV has no symbol column")
    importer.add_argument("--source", default="csv")
    importer.set_defaults(handler=command_import)

    seeder = commands.add_parser("seed-demo", help="Load synthetic demo prices for development")
    seeder.add_argument("--years", type=int, default=3)
    seeder.add_argument("--seed", type=int, default=7)
    seeder.set_defaults(handler=command_seed_demo)

    trainer = commands.add_parser("train", help="Train and activate a new XGBoost model")
    trainer.add_argument("--horizon", type=int)
    trainer.add_argument("--threshold", type=float)
    trainer.set_defaults(handler=command_train)

    commands.add_parser("generate", help="Generate signals with the active model").set_defaults(handler=command_generate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
