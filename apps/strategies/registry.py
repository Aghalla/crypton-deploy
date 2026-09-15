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
    Select exactly ONE strategy: the strongest eligible candidate whose
    setup matches the current market regime.

    Returns (best_result, reason_fa) — best_result is None when nothing
    clearly matches (caller must produce WAIT).
    """
    by_name = {r.name: r for r in strategy_results}
    regime_name = getattr(regime, 'regime', 'quiet')
    preferred = REGIME_STRATEGY_MATCH.get(regime_name, [])

    # Collect eligible candidates: must be in the preferred list, have a
    # BUY or SELL signal, and exceed the minimum strength threshold.
    candidates = []
    for name in preferred:
        result = by_name.get(name)
        if result is None:
            continue
        if result.signal in ('BUY', 'SELL') and result.strength >= MIN_SELECTED_STRENGTH:
            candidates.append(result)

    if not candidates:
        active = [r for r in strategy_results if r.signal in ('BUY', 'SELL')]
        if active:
            names = '، '.join(f'{r.name_fa} ({r.strength:.0f}٪)' for r in active)
            reason = (
                f'استراتژی‌های فعال ({names}) با رژیم {regime_name} '
                f'تطابق کافی ندارند؛ هیچ استراتژی مناسبی برای ورود وجود ندارد.'
            )
        else:
            reason = f'هیچ استراتژی‌ای سیگنال فعال نداده است (رژیم: {regime_name}).'
        return None, reason

    # Pick the STRONGEST candidate.
    candidates.sort(key=lambda r: r.strength, reverse=True)
    best = candidates[0]

    # If the top two are extremely close (within 5 pts) prefer WAIT rather
    # than forcing a choice the system cannot confidently make.
    if len(candidates) >= 2 and (candidates[0].strength - candidates[1].strength) < 5.0:
        names = (f'{candidates[0].name_fa} ({candidates[0].strength:.0f}٪) و '
                 f'{candidates[1].name_fa} ({candidates[1].strength:.0f}٪)')
        reason = (
            f'دو استراتژی {names} تقریباً هم‌سطح هستند و تفکیک دقیق ممکن نیست؛ '
            f'صبر منطقی‌تر است.'
        )
        return None, reason

    reason = (
        f'بازار {regime_name} است و استراتژی {best.name_fa} '
        f'با قدرت {best.strength:.0f}٪ بهترین تطابق با شرایط فعلی دارد.'
    )
    return best, reason
