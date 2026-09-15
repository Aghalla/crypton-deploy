"""
Multi-timeframe analysis: 1h main trend, 30m trend strength,
15m entry zone, 5m entry confirmation.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from apps.analysis.engine.indicators import add_all_indicators
from apps.analysis.engine.structure import StructureResult, analyze_structure


@dataclass
class TimeframeSnapshot:
    timeframe: str
    price: float = 0.0
    trend: str = 'sideways'
    trend_strength: float = 0.0
    ema_bias: str = 'neutral'          # price vs ema20/50/200 alignment
    rsi: float = 50.0
    macd_hist: float = 0.0
    atr: float = 0.0
    vol_ratio: float = 1.0
    structure: StructureResult | None = None
    notes: list = field(default_factory=list)


@dataclass
class MultiTimeframeResult:
    snapshots: dict = field(default_factory=dict)   # tf -> TimeframeSnapshot
    alignment: float = 0.0        # -100 (fully bearish) .. +100 (fully bullish)
    summary_fa: str = ''

    def bias(self) -> str:
        if self.alignment > 40:
            return 'bullish'
        if self.alignment < -40:
            return 'bearish'
        return 'neutral'

    def snapshot(self, tf: str) -> TimeframeSnapshot:
        return self.snapshots.get(tf, TimeframeSnapshot(timeframe=tf))


def snapshot_timeframe(timeframe: str, df: pd.DataFrame) -> TimeframeSnapshot:
    snap = TimeframeSnapshot(timeframe=timeframe)
    if len(df) < 60:
        return snap
    ind = add_all_indicators(df)
    last = ind.iloc[-1]
    structure = analyze_structure(ind)

    snap.price = float(last['close'])
    snap.trend = structure.trend
    snap.trend_strength = structure.trend_strength
    snap.rsi = float(last['rsi'])
    snap.macd_hist = float(last['macd_hist'])
    snap.atr = float(last['atr'])
    snap.vol_ratio = float(last['vol_ratio']) if np.isfinite(last['vol_ratio']) else 1.0
    snap.structure = structure

    # EMA alignment bias
    above = 0
    for col in ('ema20', 'ema50', 'ema200'):
        if last['close'] > last[col]:
            above += 1
        elif last['close'] < last[col]:
            above -= 1
    if last['ema20'] > last['ema50'] > last['ema200']:
        above += 2
    elif last['ema20'] < last['ema50'] < last['ema200']:
        above -= 2
    snap.ema_bias = 'bullish' if above >= 2 else 'bearish' if above <= -2 else 'neutral'

    names = {'up': 'صعودی', 'down': 'نزولی', 'sideways': 'خنثی'}
    snap.notes.append(f'روند {names.get(structure.trend)}')
    if structure.bos:
        snap.notes.append('شکست ساختار ' + ('صعودی' if structure.bos == 'bullish' else 'نزولی'))
    if structure.choch:
        snap.notes.append('تغییر کاراکتر قیمت')
    return snap


WEIGHTS = {'1h': 0.40, '30m': 0.30, '15m': 0.20, '5m': 0.10}


def analyze_multi_timeframe(dfs: dict[str, pd.DataFrame]) -> MultiTimeframeResult:
    """dfs: {'1h': df, '30m': df, '15m': df, '5m': df}"""
    result = MultiTimeframeResult()
    alignment = 0.0
    for tf, df in dfs.items():
        snap = snapshot_timeframe(tf, df)
        result.snapshots[tf] = snap
        score = 0.0
        if snap.trend == 'up':
            score += snap.trend_strength
        elif snap.trend == 'down':
            score -= snap.trend_strength
        if snap.ema_bias == 'bullish':
            score += 30
        elif snap.ema_bias == 'bearish':
            score -= 30
        if snap.rsi > 55:
            score += 10
        elif snap.rsi < 45:
            score -= 10
        if snap.macd_hist > 0:
            score += 10
        elif snap.macd_hist < 0:
            score -= 10
        alignment += max(-100, min(100, score)) * WEIGHTS.get(tf, 0.25)
    result.alignment = max(-100.0, min(100.0, alignment))

    s1h, s5m = result.snapshot('1h'), result.snapshot('5m')
    names = {'up': 'صعودی', 'down': 'نزولی', 'sideways': 'خنثی'}
    if result.alignment > 40:
        direction = 'صعودی'
    elif result.alignment < -40:
        direction = 'نزولی'
    else:
        direction = 'خنثی'
    result.summary_fa = (
        f'هم‌راستایی تایم‌فریم‌ها {direction} است. '
        f'روند ۱ ساعته {names.get(s1h.trend)} و تایید ۵ دقیقه‌ای {names.get(s5m.trend)}.'
    )
    return result
