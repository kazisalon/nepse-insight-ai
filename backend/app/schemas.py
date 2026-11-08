from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Action = Literal["BUY", "SELL", "HOLD", "NO TRADE"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompanyCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str | None = None
    sector: str | None = None


class CompanyOut(ORMModel):
    id: int
    symbol: str
    name: str | None
    sector: str | None
    is_active: bool


class CompanySummary(CompanyOut):
    first_date: date | None
    last_date: date | None
    bars: int
    last_close: float | None


class PriceBarIn(BaseModel):
    trade_date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    turnover: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "PriceBarIn":
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        return self


class PriceBarOut(ORMModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float | None


class FundamentalIn(BaseModel):
    as_of: date
    eps: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    book_value: float | None = None
    roe: float | None = None
    dividend_yield: float | None = None
    market_cap: float | None = None


class FundamentalOut(FundamentalIn, ORMModel):
    pass


class ImportResult(BaseModel):
    rows: int
    symbols: list[str]


class TrainRequest(BaseModel):
    horizon_days: int | None = Field(default=None, ge=1, le=60)
    return_threshold: float | None = Field(default=None, gt=0, lt=0.5)
    validation_fraction: float = Field(default=0.2, ge=0.1, le=0.4)
    activate: bool = True
    params: dict[str, float | int] | None = None


class ModelRunOut(ORMModel):
    id: int
    version: str
    horizon_days: int
    return_threshold: float
    params: dict
    metrics: dict
    feature_importance: dict
    train_start: date
    train_end: date
    n_samples: int
    is_active: bool
    created_at: datetime


class ModelRunSummary(ORMModel):
    id: int
    version: str
    horizon_days: int
    return_threshold: float
    n_samples: int
    is_active: bool
    created_at: datetime


class Driver(BaseModel):
    feature: str
    label: str
    value: float | None
    contribution: float
    effect: Literal["supports", "opposes"]


class InsightOut(BaseModel):
    symbol: str
    signal_date: date
    close: float
    action: Action
    confidence: float
    prob_up: float
    prob_neutral: float
    prob_down: float
    reasons: list[str]
    drivers: list[Driver]
    indicators: dict[str, float | None] = {}
    model_version: str
    horizon_days: int


class SignalOut(BaseModel):
    symbol: str
    signal_date: date
    close: float
    action: Action
    confidence: float
    prob_up: float
    prob_neutral: float
    prob_down: float
    reasons: list[str]
    drivers: list[Driver]
    model_version: str


class GenerateResult(BaseModel):
    model_version: str
    generated: int
    summary: dict[str, int]


class IndicatorPoint(BaseModel):
    trade_date: date
    close: float
    values: dict[str, float | None]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    active_model: str | None
    environment: str
