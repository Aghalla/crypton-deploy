"""
Technical indicators implemented on pandas DataFrames.

Each function takes a DataFrame with columns open/high/low/close/volume
(indexed by open_time) and returns a Series or DataFrame. All values are
floats; NaN appears during the warm-up period.
"""
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram)."""
    line = ema(series, fast) - ema(series, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(series: pd.Series, period: int = 20, std: float = 2.0):
    """Return (middle, upper, lower, bandwidth)."""
    middle = series.rolling(period).mean()
    sd = series.rolling(period).std()
    upper = middle + std * sd
    lower = middle - std * sd
    bandwidth = (upper - lower) / middle
    return middle, upper, lower, bandwidth


def vwap(df: pd.DataFrame) -> pd.Series:
    """Rolling session-agnostic VWAP over the whole window."""
    typical = (df['high'] + df['low'] + df['close']) / 3
    volume = df['volume'].replace(0, np.nan)
    return (typical * df['volume']).cumsum() / df['volume'].cumsum()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with every indicator column attached."""
    out = df.copy()
    close = out['close']
    out['ema20'] = ema(close, 20)
    out['ema50'] = ema(close, 50)
    out['ema200'] = ema(close, 200)
    out['rsi'] = rsi(close)
    macd_line, macd_signal, macd_hist = macd(close)
    out['macd'] = macd_line
    out['macd_signal'] = macd_signal
    out['macd_hist'] = macd_hist
    out['atr'] = atr(out)
    mid, up, low, bw = bollinger(close)
    out['bb_middle'], out['bb_upper'], out['bb_lower'], out['bb_width'] = mid, up, low, bw
    out['vwap'] = vwap(out)
    out['vol_ma20'] = out['volume'].rolling(20).mean()
    out['vol_ratio'] = out['volume'] / out['vol_ma20'].replace(0, np.nan)
    return out
