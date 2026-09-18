"""
Build the initial training dataset from historical 5m candles.

For each historical bar (with enough warm-up history) we recompute the exact
feature vector the live pipeline would produce, simulate a LONG and a SHORT
trade with ATR-based SL/TP, and label success by whether TP was hit before SL
within the holding window.
"""
import logging

import numpy as np
import pandas as pd

from apps.analysis.engine.indicators import add_all_indicators
from apps.analysis.engine.structure import analyze_structure
from apps.market_data.models import Coin
from apps.market_data.services.data import get_candles_df

logger = logging.getLogger('crypton.learning')

WARMUP = 220          # bars needed for ema200 + structure
STEP = 3              # sample every 3rd 5m bar (~one sample per 15 min)
MAX_TRADE_BARS = 40   # max bars for TP/SL resolution


def _synthetic_mtf(df_5m: pd.DataFrame, i: int):
    """Build a lightweight multi-timeframe snapshot from a single 5m frame."""
    from apps.analysis.engine.multitf import (MultiTimeframeResult,
                                              TimeframeSnapshot, snapshot_timeframe)
    # resample 5m up to higher timeframes around index i
    window = df_5m.iloc[max(0, i - 1200):i + 1]
    mtf = MultiTimeframeResult()
    resample_map = {'15m': '15min', '30m': '30min', '1h': '1h'}
    mtf.snapshots['5m'] = snapshot_timeframe('5m', window.tail(400))
    for tf, rule in resample_map.items():
        res = window.resample(rule, label='left', closed='left').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        mtf.snapshots[tf] = snapshot_timeframe(tf, res.tail(400))
    # alignment as weighted average of snapshot biases
    weights = {'1h': 0.4, '30m': 0.3, '15m': 0.2, '5m': 0.1}
    align = 0.0
    for tf, w in weights.items():
        s = mtf.snapshot(tf)
        v = 0.0
        if s.trend == 'up':
            v = s.trend_strength
        elif s.trend == 'down':
            v = -s.trend_strength
        if s.ema_bias == 'bullish':
            v += 30
        elif s.ema_bias == 'bearish':
            v -= 30
        align += max(-100, min(100, v)) * w
    mtf.alignment = float(np.clip(align, -100, 100))
    return mtf


def _simulate_trade(df, i: int, direction: str, sl: float, tp: float) -> bool | None:
    """Return True/False whether TP hit before SL, None if unresolved.

    Uses the exact SL/TP levels from build_trade_setup (dynamic per signal
    strength + structure), so historical labels match live trade parameters.
    """
    window = df.iloc[i + 1:i + 1 + MAX_TRADE_BARS]
    for _, bar in window.iterrows():
        if direction == 'LONG':
            if bar['low'] <= sl:
                return False
            if bar['high'] >= tp:
                return True
        else:
            if bar['high'] >= sl:
                return False
            if bar['low'] <= tp:
                return True
    return None


def build_historical_samples(coin: Coin) -> tuple[list[dict], int]:
    """Return (samples, skipped) — samples are dict rows of features+label."""
    df = get_candles_df(coin, '5m', limit=13000)   # ~45 days of 5m candles
    if len(df) < WARMUP + MAX_TRADE_BARS + 50:
        logger.warning('not enough 5m history for %s (%d rows)', coin.symbol, len(df))
        return [], 0

    ind = add_all_indicators(df)
    samples = []
    skipped = 0
    from apps.signals.confidence import compute_confidence
    from apps.signals.engine import build_feature_vector
    from apps.signals.trade_setup import build_trade_setup
    from apps.strategies.registry import run_all_strategies

    for i in range(WARMUP, len(ind) - MAX_TRADE_BARS - 1, STEP):
        row = ind.iloc[i]
        atr = float(row['atr'])
        price = float(row['close'])
        if not np.isfinite(atr) or atr <= 0 or price <= 0:
            skipped += 1
            continue

        history = ind.iloc[:i + 1]
        mtf = _synthetic_mtf(history, i)
        strategy_results = run_all_strategies(mtf, df_5m=history.tail(400))
        atr_pct = atr / price

        for direction in ('LONG', 'SHORT'):
            confidence = compute_confidence(mtf, strategy_results, direction)
            if confidence.direction not in ('LONG', 'SHORT'):
                continue
            from apps.signals.confidence import map_score_to_signal_type
            signal_type = map_score_to_signal_type(confidence.score, confidence.direction)
            setup = build_trade_setup(direction, price, atr, mtf.snapshot('5m').structure,
                                      signal_type=signal_type)
            if setup.stop_loss == 0 or setup.take_profit == 0:
                continue
            outcome = _simulate_trade(df, i, direction, setup.stop_loss, setup.take_profit)
            if outcome is None:
                continue
            feats = build_feature_vector(mtf, strategy_results, confidence, setup, atr_pct)
            samples.append({
                'features': feats,
                'label': outcome,
                'created_at': df.index[i].to_pydatetime(),
            })
    return samples, skipped
