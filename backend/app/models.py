from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(100), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prices: Mapped[list["PriceBar"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    fundamentals: Mapped[list["Fundamental"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("company_id", "trade_date", name="uq_price_company_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    turnover: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50), default="manual")

    company: Mapped[Company] = relationship(back_populates="prices")


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("company_id", "as_of", name="uq_fundamental_company_asof"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    eps: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    pb_ratio: Mapped[float | None] = mapped_column(Float)
    book_value: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    dividend_yield: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)

    company: Mapped[Company] = relationship(back_populates="fundamentals")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(50), unique=True)
    horizon_days: Mapped[int] = mapped_column(Integer)
    return_threshold: Mapped[float] = mapped_column(Float)
    params: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    feature_names: Mapped[list] = mapped_column(JSON)
    feature_importance: Mapped[dict] = mapped_column(JSON)
    train_start: Mapped[date] = mapped_column(Date)
    train_end: Mapped[date] = mapped_column(Date)
    n_samples: Mapped[int] = mapped_column(Integer)
    artifact_path: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("company_id", "model_run_id", "signal_date", name="uq_signal_company_model_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(10), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    prob_up: Mapped[float] = mapped_column(Float)
    prob_neutral: Mapped[float] = mapped_column(Float)
    prob_down: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSON)
    drivers: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship()
    model_run: Mapped[ModelRun] = relationship()
