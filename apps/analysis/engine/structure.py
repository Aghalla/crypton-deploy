"""
Market structure analysis: swing points, HH/HL/LH/LL labelling,
Break of Structure (BOS) and Change of Character (CHoCH), trend detection.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SwingPoint:
    index: int          # positional index in the candle array
    time: pd.Timestamp
    price: float
    kind: str           # 'high' | 'low'
    label: str = ''     # HH / HL / LH / LL


@dataclass
class StructureResult:
    trend: str = 'sideways'          # 'up' | 'down' | 'sideways'
    trend_strength: float = 0.0      # 0..100
    swings: list = field(default_factory=list)
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    bos: str = ''                    # 'bullish' | 'bearish' | ''
    choch: str = ''                  # 'bullish' | 'bearish' | ''
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)

    def summary_fa(self) -> str:
        names = {'up': 'صعودی', 'down': 'نزولی', 'sideways': 'خنثی'}
        text = f'روند ساختاری {names.get(self.trend, self.trend)}'
        if self.bos:
            text += f' با شکست ساختار {"صعودی" if self.bos == "bullish" else "نزولی"}'
        if self.choch:
            text += ' و تغییر کاراکتر قیمت'
        return text


def _find_swings(df: pd.DataFrame, lookback: int = 3) -> list[SwingPoint]:
    """Simple fractal swing detection: a high/low larger than `lookback` bars on both sides."""
    highs = df['high'].values
    lows = df['low'].values
    times = df.index
    swings = []
    n = len(df)
    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback:i + lookback + 1]
        window_l = lows[i - lookback:i + lookback + 1]
        if highs[i] == window_h.max():
            swings.append(SwingPoint(i, times[i], float(highs[i]), 'high'))
        if lows[i] == window_l.min():
            swings.append(SwingPoint(i, times[i], float(lows[i]), 'low'))
    return _label_swings(swings)


def _label_swings(swings: list[SwingPoint]) -> list[SwingPoint]:
    highs = [s for s in swings if s.kind == 'high']
    lows = [s for s in swings if s.kind == 'low']
    for i in range(1, len(highs)):
        prev, cur = highs[i - 1], highs[i]
        cur.label = 'HH' if cur.price > prev.price else 'LH'
    for i in range(1, len(lows)):
        prev, cur = lows[i - 1], lows[i]
        cur.label = 'HL' if cur.price > prev.price else 'LL'
    return swings


def analyze_structure(df: pd.DataFrame, lookback: int = 3) -> StructureResult:
    """Detect trend / BOS / CHoCH and support-resistance zones."""
    result = StructureResult()
    if len(df) < lookback * 2 + 10:
        return result

    swings = _find_swings(df, lookback)
    result.swings = swings
    highs = [s for s in swings if s.kind == 'high']
    lows = [s for s in swings if s.kind == 'low']
    if highs:
        result.last_high = highs[-1]
    if lows:
        result.last_low = lows[-1]

    recent_highs = highs[-3:] if len(highs) >= 3 else highs
    recent_lows = lows[-3:] if len(lows) >= 3 else lows
    hh = sum(1 for s in recent_highs if s.label == 'HH')
    lh = sum(1 for s in recent_highs if s.label == 'LH')
    hl = sum(1 for s in recent_lows if s.label == 'HL')
    ll = sum(1 for s in recent_lows if s.label == 'LL')

    # trend from the majority of recent labelled swings
    bull = hh + hl
    bear = lh + ll
    total = bull + bear
    if total == 0:
        result.trend = 'sideways'
        result.trend_strength = 0.0
    else:
        ratio = bull / total
        if ratio >= 0.7:
            result.trend, result.trend_strength = 'up', (ratio - 0.5) * 200
        elif ratio <= 0.3:
            result.trend, result.trend_strength = 'down', (0.5 - ratio) * 200
        else:
            result.trend, result.trend_strength = 'sideways', abs(ratio - 0.5) * 200

    # BOS / CHoCH against the last confirmed swing levels
    close = float(df['close'].iloc[-1])
    last_high_px = result.last_high.price if result.last_high else np.nan
    last_low_px = result.last_low.price if result.last_low else np.nan
    prev_close = float(df['close'].iloc[-2])
    if not np.isnan(last_high_px) and prev_close <= last_high_px < close:
        if result.trend == 'up':
            result.bos = 'bullish'
        else:
            result.choch = 'bullish'   # broke structure against a downtrend
    if not np.isnan(last_low_px) and prev_close >= last_low_px > close:
        if result.trend == 'down':
            result.bos = 'bearish'
        else:
            result.choch = 'bearish'

    # support / resistance zones from clustered swing prices near current price
    # levels sorted ascending: nearest resistance = first above close,
    # nearest support = last below close
    levels = sorted({round(s.price, 8) for s in swings[-12:]})
    above = [p for p in levels if p > close]
    below = [p for p in levels if p < close]
    result.resistance_levels = above[:3]     # nearest 3 resistances (closest to price)
    result.support_levels = below[-3:] if below else []  # nearest 3 supports (closest to price)
    return result
