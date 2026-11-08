import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100 - 100 / (1 + rs)
    return result.where(loss != 0, 100.0).where(gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return line, signal_line, line - signal_line


def bollinger(close: pd.Series, period: int = 20, width: float = 2.0) -> tuple[pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + width * std
    lower = mid - width * std
    band = (upper - lower).replace(0, np.nan)
    return (close - lower) / band, band / mid


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    return 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)


def on_balance_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def compute_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.sort_values("trade_date").copy()
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    daily_return = close.pct_change()

    for window in (1, 5, 10, 20, 60):
        df[f"ret_{window}"] = close.pct_change(window)

    for window in (10, 20, 50):
        df[f"sma_{window}"] = close.rolling(window).mean()
        df[f"close_vs_sma_{window}"] = close / df[f"sma_{window}"] - 1
    df["sma_10_vs_50"] = df["sma_10"] / df["sma_50"] - 1

    macd_line, macd_signal, macd_hist = macd(close)
    df["macd"] = macd_line / close
    df["macd_signal"] = macd_signal / close
    df["macd_hist"] = macd_hist / close

    df["rsi_14"] = rsi(close)
    df["stoch_k_14"] = stochastic_k(high, low, close)
    df["bb_pct_b"], df["bb_width"] = bollinger(close)
    df["atr_pct_14"] = atr(high, low, close) / close
    df["volatility_20"] = daily_return.rolling(20).std()

    volume_sma_20 = volume.rolling(20).mean()
    df["volume_ratio_20"] = volume / volume_sma_20.replace(0, np.nan)
    df["volume_trend_5_20"] = volume.rolling(5).mean() / volume_sma_20.replace(0, np.nan)
    obv = on_balance_volume(close, volume)
    df["obv_trend_20"] = obv.diff(20) / volume.rolling(20).sum().replace(0, np.nan)

    window_high = high.rolling(250, min_periods=60).max()
    window_low = low.rolling(250, min_periods=60).min()
    df["dist_from_high_250"] = close / window_high - 1
    df["dist_from_low_250"] = close / window_low - 1

    turnover = df["turnover"].fillna(close * volume) if "turnover" in df else close * volume
    df["avg_turnover_20"] = turnover.rolling(20).mean()
    df["log_turnover_20"] = np.log1p(df["avg_turnover_20"])
    df["history_days"] = np.arange(1, len(df) + 1)
    return df
