"""Strategy contract shared by every strategy module."""
from dataclasses import dataclass, field


@dataclass
class StrategyResult:
    name: str                     # english key, e.g. 'trend_following'
    name_fa: str                  # displayed Persian name
    signal: str = 'WAIT'          # BUY / SELL / WAIT
    strength: float = 0.0         # 0..100
    explanation_fa: str = ''
    supporting: dict = field(default_factory=dict)   # raw numbers behind the decision

    def to_dict(self):
        return {
            'name': self.name,
            'name_fa': self.name_fa,
            'signal': self.signal,
            'strength': round(self.strength, 1),
            'explanation': self.explanation_fa,
            'supporting': self.supporting,
        }


class BaseStrategy:
    """Subclasses implement evaluate(mtf) and return a StrategyResult."""
    name = ''
    name_fa = ''

    def evaluate(self, mtf) -> StrategyResult:
        raise NotImplementedError
