import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Fundamental, PriceBar
from app.services.indicators import compute_indicators

CLASS_LABELS = ["down", "neutral", "up"]

TECHNICAL_FEATURES = [
    "ret_1",
    "ret_5",
    "ret_10",
    "ret_20",
    "ret_60",
    "close_vs_sma_10",
    "close_vs_sma_20",
    "close_vs_sma_50",
    "sma_10_vs_50",
    "macd",
    "macd_signal",
    "macd_hist",
    "rsi_14",
    "stoch_k_14",
    "bb_pct_b",
    "bb_width",
    "atr_pct_14",
    "volatility_20",
    "volume_ratio_20",
    "volume_trend_5_20",
    "obv_trend_20",
    "dist_from_high_250",
    "dist_from_low_250",
    "log_turnover_20",
]

MARKET_FEATURES = ["market_ret_5", "market_ret_20", "relative_strength_20", "market_breadth_50"]

FUNDAMENTAL_FEATURES = ["pe_ratio", "pb_ratio", "roe", "dividend_yield", "earnings_yield"]

FEATURE_COLUMNS = TECHNICAL_FEATURES + MARKET_FEATURES + FUNDAMENTAL_FEATURES

FEATURE_LABELS = {
    "ret_1": "1-day return",
    "ret_5": "5-day return",
    "ret_10": "10-day return",
    "ret_20": "20-day return",
    "ret_60": "60-day return",
    "close_vs_sma_10": "Price vs 10-day average",
    "close_vs_sma_20": "Price vs 20-day average",
    "close_vs_sma_50": "Price vs 50-day average",
    "sma_10_vs_50": "Short vs long trend",
    "macd": "MACD",
    "macd_signal": "MACD signal line",
    "macd_hist": "MACD histogram",
    "rsi_14": "RSI (14)",
    "stoch_k_14": "Stochastic %K",
    "bb_pct_b": "Bollinger %B",
    "bb_width": "Bollinger band width",
    "atr_pct_14": "Average true range",
    "volatility_20": "20-day volatility",
    "volume_ratio_20": "Volume vs 20-day average",
    "volume_trend_5_20": "Short-term volume trend",
    "obv_trend_20": "On-balance volume trend",
    "dist_from_high_250": "Distance from 52-week high",
    "dist_from_low_250": "Distance from 52-week low",
    "log_turnover_20": "Liquidity (turnover)",
    "market_ret_5": "Market 5-day return",
    "market_ret_20": "Market 20-day return",
    "relative_strength_20": "Relative strength vs market",
    "market_breadth_50": "Market breadth",
    "pe_ratio": "P/E ratio",
    "pb_ratio": "P/B ratio",
    "roe": "Return on equity",
    "dividend_yield": "Dividend yield",
    "earnings_yield": "Earnings yield",
}


def load_prices(db: Session, symbols: list[str] | None = None) -> pd.DataFrame:
    query = (
        select(
            Company.symbol,
            Company.sector,
            PriceBar.trade_date,
            PriceBar.open,
            PriceBar.high,
            PriceBar.low,
            PriceBar.close,
            PriceBar.volume,
            PriceBar.turnover,
        )
        .join(PriceBar, PriceBar.company_id == Company.id)
        .where(Company.is_active.is_(True))
        .order_by(Company.symbol, PriceBar.trade_date)
    )
    if symbols:
        query = query.where(Company.symbol.in_([symbol.upper() for symbol in symbols]))
    frame = pd.DataFrame(db.execute(query).all())
    if frame.empty:
        return frame
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


def load_fundamentals(db: Session) -> pd.DataFrame:
    query = select(
        Company.symbol,
        Fundamental.as_of,
        Fundamental.eps,
        Fundamental.pe_ratio,
        Fundamental.pb_ratio,
        Fundamental.roe,
        Fundamental.dividend_yield,
    ).join(Fundamental, Fundamental.company_id == Company.id)
    frame = pd.DataFrame(db.execute(query).all())
    if not frame.empty:
        frame["as_of"] = pd.to_datetime(frame["as_of"])
    return frame


def _add_market_features(frame: pd.DataFrame) -> pd.DataFrame:
    daily = frame.groupby("trade_date").agg(
        market_ret_1=("ret_1", "mean"),
        market_breadth_50=("close_vs_sma_50", lambda values: (values > 0).mean() if values.notna().any() else np.nan),
    )
    daily = daily.sort_index()
    market_index = (1 + daily["market_ret_1"].fillna(0)).cumprod()
    daily["market_ret_5"] = market_index.pct_change(5)
    daily["market_ret_20"] = market_index.pct_change(20)
    frame = frame.merge(daily[["market_ret_5", "market_ret_20", "market_breadth_50"]], on="trade_date", how="left")
    frame["relative_strength_20"] = frame["ret_20"] - frame["market_ret_20"]
    return frame


def _add_fundamental_features(frame: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    if fundamentals.empty:
        for column in ("pe_ratio", "pb_ratio", "roe", "dividend_yield", "eps"):
            frame[column] = np.nan
    else:
        frame = pd.merge_asof(
            frame.sort_values("trade_date"),
            fundamentals.sort_values("as_of"),
            left_on="trade_date",
            right_on="as_of",
            by="symbol",
            direction="backward",
        ).drop(columns=["as_of"])
    frame["earnings_yield"] = frame["eps"] / frame["close"]
    return frame


def build_feature_frame(db: Session, symbols: list[str] | None = None) -> pd.DataFrame:
    prices = load_prices(db)
    if prices.empty:
        return prices
    frames = [compute_indicators(group) for _, group in prices.groupby("symbol", sort=False)]
    frame = pd.concat(frames, ignore_index=True)
    frame = _add_market_features(frame)
    frame = _add_fundamental_features(frame, load_fundamentals(db))
    frame = frame.replace([np.inf, -np.inf], np.nan)
    if symbols:
        frame = frame[frame["symbol"].isin([symbol.upper() for symbol in symbols])]
    return frame.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def add_targets(frame: pd.DataFrame, horizon: int, threshold: float) -> pd.DataFrame:
    frame = frame.copy()
    future_close = frame.groupby("symbol")["close"].shift(-horizon)
    frame["forward_return"] = future_close / frame["close"] - 1
    frame["target"] = np.select(
        [frame["forward_return"] > threshold, frame["forward_return"] < -threshold],
        [2, 0],
        default=1,
    )
    frame.loc[frame["forward_return"].isna(), "target"] = -1
    return frame
