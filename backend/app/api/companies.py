from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Fundamental, PriceBar
from app.schemas import (
    CompanyCreate,
    CompanyOut,
    CompanySummary,
    FundamentalIn,
    FundamentalOut,
    ImportResult,
    IndicatorPoint,
    PriceBarIn,
    PriceBarOut,
)
from app.services.features import FEATURE_COLUMNS, build_feature_frame
from app.services.ingestion import IngestionError, clean_price_frame, ensure_companies, parse_price_csv, upsert_fundamentals, upsert_prices

router = APIRouter(tags=["market data"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def get_company(db: Session, symbol: str) -> Company:
    company = db.scalar(select(Company).where(Company.symbol == symbol.upper()))
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Company {symbol.upper()} not found")
    return company


@router.get("/companies", response_model=list[CompanySummary])
def list_companies(sector: str | None = None, db: Session = Depends(get_db)) -> list[CompanySummary]:
    stats = (
        select(
            PriceBar.company_id,
            func.min(PriceBar.trade_date).label("first_date"),
            func.max(PriceBar.trade_date).label("last_date"),
            func.count().label("bars"),
        )
        .group_by(PriceBar.company_id)
        .subquery()
    )
    last_close = (
        select(PriceBar.close)
        .where(PriceBar.company_id == Company.id)
        .order_by(PriceBar.trade_date.desc())
        .limit(1)
        .scalar_subquery()
    )
    query = (
        select(Company, stats.c.first_date, stats.c.last_date, func.coalesce(stats.c.bars, 0), last_close)
        .outerjoin(stats, stats.c.company_id == Company.id)
        .order_by(Company.symbol)
    )
    if sector:
        query = query.where(Company.sector == sector)
    return [
        CompanySummary(
            **CompanyOut.model_validate(company).model_dump(),
            first_date=first_date,
            last_date=last_date,
            bars=bars,
            last_close=close,
        )
        for company, first_date, last_date, bars, close in db.execute(query).all()
    ]


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)) -> Company:
    symbol = payload.symbol.strip().upper()
    ensure_companies(db, [symbol], {symbol: payload.model_dump(exclude={"symbol"}, exclude_none=True)})
    db.commit()
    return get_company(db, symbol)


@router.get("/companies/{symbol}", response_model=CompanyOut)
def read_company(symbol: str, db: Session = Depends(get_db)) -> Company:
    return get_company(db, symbol)


@router.get("/companies/{symbol}/prices", response_model=list[PriceBarOut])
def read_prices(
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[PriceBar]:
    company = get_company(db, symbol)
    query = select(PriceBar).where(PriceBar.company_id == company.id)
    if start:
        query = query.where(PriceBar.trade_date >= start)
    if end:
        query = query.where(PriceBar.trade_date <= end)
    rows = db.scalars(query.order_by(PriceBar.trade_date.desc()).limit(limit)).all()
    return list(reversed(rows))


@router.post("/companies/{symbol}/prices", response_model=ImportResult)
def add_prices(symbol: str, bars: list[PriceBarIn], db: Session = Depends(get_db)) -> ImportResult:
    if not bars:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No price bars supplied")
    frame = pd.DataFrame([bar.model_dump() for bar in bars])
    frame["symbol"] = symbol.upper()
    rows = upsert_prices(db, clean_price_frame(frame), source="api")
    return ImportResult(rows=rows, symbols=[symbol.upper()])


@router.post("/prices/import", response_model=ImportResult)
async def import_prices(
    file: UploadFile = File(...),
    symbol: str | None = Form(default=None),
    source: str = Form(default="csv"),
    db: Session = Depends(get_db),
) -> ImportResult:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 50 MB")
    try:
        frame = parse_price_csv(content, symbol.upper() if symbol else None)
    except IngestionError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    rows = upsert_prices(db, frame, source=source)
    return ImportResult(rows=rows, symbols=sorted(frame["symbol"].unique().tolist()))


@router.get("/companies/{symbol}/fundamentals", response_model=list[FundamentalOut])
def read_fundamentals(symbol: str, db: Session = Depends(get_db)) -> list[Fundamental]:
    company = get_company(db, symbol)
    return list(db.scalars(select(Fundamental).where(Fundamental.company_id == company.id).order_by(Fundamental.as_of)))


@router.post("/companies/{symbol}/fundamentals", response_model=ImportResult)
def add_fundamentals(symbol: str, rows: list[FundamentalIn], db: Session = Depends(get_db)) -> ImportResult:
    count = upsert_fundamentals(db, symbol, [row.model_dump() for row in rows])
    return ImportResult(rows=count, symbols=[symbol.upper()])


@router.get("/companies/{symbol}/indicators", response_model=list[IndicatorPoint])
def read_indicators(
    symbol: str,
    limit: int = Query(default=120, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[IndicatorPoint]:
    get_company(db, symbol)
    frame = build_feature_frame(db, [symbol]).tail(limit)
    frame = frame.astype(object).where(frame.notna(), None)
    return [
        IndicatorPoint(
            trade_date=row["trade_date"].date(),
            close=row["close"],
            values={column: row[column] for column in FEATURE_COLUMNS + ["sma_20", "sma_50"]},
        )
        for _, row in frame.iterrows()
    ]
