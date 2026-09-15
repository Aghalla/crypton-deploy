"""Registry that runs every strategy and combines their votes."""
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
