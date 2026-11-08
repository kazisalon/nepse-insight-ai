import io

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Company, Fundamental, PriceBar

COLUMN_ALIASES = {
    "symbol": ["symbol", "stock_symbol", "ticker", "scrip"],
    "trade_date": ["trade_date", "date", "business_date", "businessdate", "as_of_date"],
    "open": ["open", "open_price", "openprice"],
    "high": ["high", "high_price", "highprice", "max_price"],
    "low": ["low", "low_price", "lowprice", "min_price"],
    "close": ["close", "close_price", "closeprice", "ltp", "last_traded_price"],
    "volume": ["volume", "qty", "quantity", "total_traded_quantity", "traded_shares", "totaltradedquantity"],
    "turnover": ["turnover", "amount", "total_traded_amount", "totaltradedvalue", "total_traded_value"],
}

REQUIRED_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close", "volume"]


class IngestionError(ValueError):
    pass


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    lookup = {column.strip().lower().replace(" ", "_").replace("-", "_"): column for column in frame.columns}
    rename = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                rename[lookup[alias]] = target
                break
    return frame.rename(columns=rename)


def parse_price_csv(content: bytes, default_symbol: str | None = None) -> pd.DataFrame:
    try:
        frame = pd.read_csv(io.BytesIO(content), thousands=",")
    except Exception as error:
        raise IngestionError(f"Unable to read CSV: {error}") from error
    frame = _normalise_columns(frame)
    if "symbol" not in frame and default_symbol:
        frame["symbol"] = default_symbol
    return clean_price_frame(frame)


def clean_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise IngestionError(f"Missing required columns: {', '.join(missing)}")

    frame = frame.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    for column in ("open", "high", "low", "close", "volume", "turnover"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "turnover" not in frame:
        frame["turnover"] = frame["close"] * frame["volume"]

    frame = frame.dropna(subset=REQUIRED_COLUMNS)
    frame = frame[(frame["close"] > 0) & (frame["high"] >= frame["low"]) & (frame["volume"] >= 0)]
    frame = frame.drop_duplicates(subset=["symbol", "trade_date"], keep="last")
    if frame.empty:
        raise IngestionError("No valid price rows found")
    return frame[REQUIRED_COLUMNS + ["turnover"]]


def ensure_companies(db: Session, symbols: list[str], details: dict[str, dict] | None = None) -> dict[str, int]:
    details = details or {}
    rows = [{"symbol": symbol, **details.get(symbol, {})} for symbol in sorted(set(symbols))]
    if rows:
        statement = insert(Company).values(rows)
        update_columns = {key: statement.excluded[key] for key in ("name", "sector") if any(key in row for row in rows)}
        statement = (
            statement.on_conflict_do_update(index_elements=["symbol"], set_=update_columns)
            if update_columns
            else statement.on_conflict_do_nothing(index_elements=["symbol"])
        )
        db.execute(statement)
    result = db.execute(select(Company.symbol, Company.id).where(Company.symbol.in_(symbols)))
    return {symbol: company_id for symbol, company_id in result}


def upsert_prices(db: Session, frame: pd.DataFrame, source: str = "manual", chunk_size: int = 5000) -> int:
    company_ids = ensure_companies(db, frame["symbol"].unique().tolist())
    records = [
        {
            "company_id": company_ids[row.symbol],
            "trade_date": row.trade_date,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
            "turnover": None if pd.isna(row.turnover) else float(row.turnover),
            "source": source,
        }
        for row in frame.itertuples(index=False)
    ]
    for start in range(0, len(records), chunk_size):
        statement = insert(PriceBar).values(records[start : start + chunk_size])
        statement = statement.on_conflict_do_update(
            constraint="uq_price_company_date",
            set_={
                key: statement.excluded[key]
                for key in ("open", "high", "low", "close", "volume", "turnover", "source")
            },
        )
        db.execute(statement)
    db.commit()
    return len(records)


def upsert_fundamentals(db: Session, symbol: str, rows: list[dict]) -> int:
    company_id = ensure_companies(db, [symbol.upper()])[symbol.upper()]
    records = [{"company_id": company_id, **row} for row in rows]
    if not records:
        return 0
    statement = insert(Fundamental).values(records)
    statement = statement.on_conflict_do_update(
        constraint="uq_fundamental_company_asof",
        set_={
            key: statement.excluded[key]
            for key in ("eps", "pe_ratio", "pb_ratio", "book_value", "roe", "dividend_yield", "market_cap")
        },
    )
    db.execute(statement)
    db.commit()
    return len(records)
