"""Registry that runs every strategy, plus regime-based single-strategy selection."""
from apps.strategies.base import StrategyResult
from apps.strategies.breakout import BreakoutStrategy
from apps.strategies.momentum import MomentumStrategy
from apps.strategies.pullback import PullbackStrategy
from apps.strategies.range import RangeStrategy
from apps.strategies.trend_following import TrendFollowingStrategy

STRATEGIES = [
    TrendFollowingStrategy(),
    BreakoutStrategy(),
    PullbackStrategy(),
    MomentumStrategy(),
    RangeStrategy(),
]

# Priority list of strategies that match each regime, best-match first.
REGIME_STRATEGY_MATCH = {
    'trending': ['trend_following', 'pullback', 'momentum'],
    'range': ['range', 'breakout'],
    'volatile': ['breakout', 'momentum'],
    'quiet': ['range', 'trend_following'],
}

# Minimum strength (0-100) for the selected strategy to be considered valid
MIN_SELECTED_STRENGTH = 35.0


def run_all_strategies(mtf, df_5m=None, regime_weights=None) -> list[StrategyResult]:
    results = []
    for strategy in STRATEGIES:
        if strategy.name == 'breakout':
            result = strategy.evaluate(mtf, df_5m=df_5m)
        else:
            result = strategy.evaluate(mtf)
        # apply regime-based weight multiplier
        if regime_weights and strategy.name in regime_weights:
            result.strength *= regime_weights[strategy.name]
            result.strength = min(100.0, result.strength)
            result.supporting['regime_weight'] = round(regime_weights[strategy.name], 2)
        results.append(result)
    return results


def select_best_strategy(regime, strategy_results) -> tuple:
    """
    Select exactly ONE strategy whose setup matches the current regime.

    Returns (best_result, reason_fa) — best_result is None when nothing
    clearly matches (caller must produce WAIT).
    """
    by_name = {r.name: r for r in strategy_results}
    regime_name = getattr(regime, 'regime', 'quiet')
    preferred = REGIME_STRATEGY_MATCH.get(regime_name, ['trend_following'])

    for name in preferred:
        result = by_name.get(name)
        if result is None:
            continue
        if result.signal in ('BUY', 'SELL') and result.strength >= MIN_SELECTED_STRENGTH:
            reason = (
                f'بازار {regime_name} است و استراتژی {result.name_fa} '
                f'با قدرت {result.strength:.0f}٪ بهترین تطابق با شرایط فعلی دارد.'
            )
            return result, reason

    # nothing in the preferred list fired strongly enough
    active = [r for r in strategy_results if r.signal in ('BUY', 'SELL')]
    if active:
        names = '، '.join(f'{r.name_fa} ({r.strength:.0f}٪)' for r in active)
        reason = (
            f'استراتژی‌های فعال ({names}) با رژیم {regime_name} تطابق کافی ندارند؛ '
            f'هیچ استراتژی مناسبی برای ورود وجود ندارد.'
        )
    else:
        reason = f'هیچ استراتژی‌ای سیگنال فعال نداده است (رژیم: {regime_name}).'
    return None, reason
