"""
Market Regime Detection: identifies the current market condition
(trending/range, high/low volatility) and assigns weights to strategies.

Used by the strategy engine and confidence engine to adapt behavior.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from apps.analysis.engine.indicators import add_all_indicators


@dataclass
class RegimeResult:
    regime: str = 'unknown'       # trending / range / volatile / quiet
    direction: str = 'neutral'    # bullish / bearish / neutral
    volatility: str = 'normal'    # high / normal / low
    trend_strength: float = 0.0   # 0..100
    range_score: float = 0.0      # 0..100 (higher = more range-bound)
    vol_pct: float = 0.0          # current ATR as % of price
    strategy_weights: dict = field(default_factory=dict)
    summary_fa: str = ''

    def to_dict(self):
        return {
            'regime': self.regime,
            'direction': self.direction,
            'volatility': self.volatility,
            'trend_strength': round(self.trend_strength, 1),
            'range_score': round(self.range_score, 1),
            'vol_pct': round(self.vol_pct * 100, 2),
            'strategy_weights': {k: round(v, 2) for k, v in self.strategy_weights.items()},
        }


def detect_regime(df_5m: pd.DataFrame, df_1h: pd.DataFrame | None = None) -> RegimeResult:
    """
    Detect market regime from 5m candles (and optionally 1h).

    Uses:
    - ADX-like metric from EMA spread for trend strength
    - Bollinger Band width for volatility / range
    - ATR percentage for volatility classification
    - Price position relative to EMA for direction
    """
    result = RegimeResult()
    if len(df_5m) < 100:
        result.summary_fa = 'داده کافی برای تشخیص وضعیت بازار نیست'
        result.strategy_weights = _default_weights()
        return result

    # --- Direction from 1h EMAs when available (more authoritative than 5m);
    # fall back to 5m otherwise ---
    direction_df = None
    if df_1h is not None and len(df_1h) >= 60:
        direction_df = df_1h
    elif len(df_5m) >= 200:
        direction_df = df_5m
    if direction_df is not None:
        d_ind = add_all_indicators(direction_df)
        d_last = d_ind.iloc[-1]
        spread = abs(d_last['ema20'] - d_last['ema200']) / d_last['close'] if d_last['close'] else 0
        if d_last['ema20'] > d_last['ema50'] > d_last['ema200']:
            result.direction = 'bullish'
            result.trend_strength = min(100, spread * 2000 + 40)
        elif d_last['ema20'] < d_last['ema50'] < d_last['ema200']:
            result.direction = 'bearish'
            result.trend_strength = min(100, spread * 2000 + 40)
        else:
            result.direction = 'neutral'
            result.trend_strength = max(0, 40 - spread * 1000)

    ind = add_all_indicators(df_5m)
    last = ind.iloc[-1]
    close = last['close']

    # --- Bollinger Band width for range detection ---
    bb_width = last['bb_width']
    if np.isfinite(bb_width):
        # narrow bands = range market
        result.range_score = max(0, min(100, (0.04 - bb_width) / 0.04 * 100))
        result.range_score = max(0, result.range_score)

    # --- ATR-based volatility ---
    atr_pct = last['atr'] / close if close > 0 else 0
    result.vol_pct = atr_pct
    if atr_pct > 0.015:
        result.volatility = 'high'
    elif atr_pct < 0.004:
        result.volatility = 'low'
    else:
        result.volatility = 'normal'

    # --- Classify regime ---
    if result.trend_strength > 50:
        result.regime = 'trending'
    elif result.range_score > 50:
        result.regime = 'range'
    elif result.volatility == 'high':
        result.regime = 'volatile'
    elif result.volatility == 'low':
        result.regime = 'quiet'
    else:
        result.regime = 'trending' if result.trend_strength > 25 else 'range'

    # --- Strategy weights based on regime ---
    result.strategy_weights = _weights_for_regime(result)

    # --- Summary ---
    regime_fa = {'trending': 'رونددار', 'range': 'محدوده‌ای', 'volatile': 'پرنوسان', 'quiet': 'کم‌نوسان'}
    dir_fa = {'bullish': 'صعودی', 'bearish': 'نزولی', 'neutral': 'خنثی'}
    vol_fa = {'high': 'بالا', 'normal': 'عادی', 'low': 'پایین'}
    result.summary_fa = (
        f'بازار {regime_fa.get(result.regime)} {dir_fa.get(result.direction)}. '
        f'نوسان {vol_fa.get(result.volatility)} (ATR ≈ {atr_pct:.2%}). '
        f'قدرت روند {result.trend_strength:.0f}/۱۰۰.'
    )
    return result


# Default strategy weights (equal)
_DEFAULT_W = {
    'trend_following': 1.0,
    'breakout': 1.0,
    'pullback': 1.0,
    'momentum': 1.0,
    'range': 1.0,
}


def _default_weights() -> dict:
    return dict(_DEFAULT_W)


def _weights_for_regime(regime: RegimeResult) -> dict:
    """Adjust strategy weights based on detected regime."""
    w = dict(_DEFAULT_W)
    if regime.regime == 'trending':
        w['trend_following'] = 1.8
        w['pullback'] = 1.4
        w['momentum'] = 1.2
        w['range'] = 0.4
        w['breakout'] = 1.0
    elif regime.regime == 'range':
        w['range'] = 1.8
        w['breakout'] = 1.3
        w['momentum'] = 0.8
        w['trend_following'] = 0.5
        w['pullback'] = 0.7
    elif regime.regime == 'volatile':
        w['breakout'] = 1.5
        w['momentum'] = 1.3
        w['trend_following'] = 0.8
        w['pullback'] = 0.9
        w['range'] = 0.6
    elif regime.regime == 'quiet':
        w['range'] = 1.3
        w['trend_following'] = 1.1
        w['breakout'] = 0.7
        w['pullback'] = 1.0
        w['momentum'] = 0.8
    return w
