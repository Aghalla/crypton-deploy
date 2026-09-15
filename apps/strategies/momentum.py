"""Momentum: RSI + MACD + volume agreement."""
from apps.strategies.base import BaseStrategy, StrategyResult


class MomentumStrategy(BaseStrategy):
    name = 'momentum'
    name_fa = 'مومنتوم'

    def evaluate(self, mtf) -> StrategyResult:
        res = StrategyResult(name=self.name, name_fa=self.name_fa)
        m5 = mtf.snapshot('5m')
        m15 = mtf.snapshot('15m')

        score = 0.0
        notes = []

        # RSI momentum zone
        if m5.rsi >= 60:
            score += 25
            notes.append(f'RSI پنج‌دقیقه در ناحیه مومنتوم صعودی ({m5.rsi:.0f})')
        elif m5.rsi <= 40:
            score -= 25
            notes.append(f'RSI پنج‌دقیقه در ناحیه مومنتوم نزولی ({m5.rsi:.0f})')
        if m5.rsi > 78:
            score -= 10
            notes.append('هشدار: اشباع خرید ممکن است اصلاح ایجاد کند')
        if m5.rsi < 22:
            score += 10
            notes.append('هشدار: اشباع فروش ممکن است بازگشت ایجاد کند')

        # MACD histogram agreement across 5m and 15m
        if m5.macd_hist > 0 and m15.macd_hist > 0:
            score += 25
            notes.append('هیستوگرام MACD در ۵ و ۱۵ دقیقه مثبت است')
        elif m5.macd_hist < 0 and m15.macd_hist < 0:
            score -= 25
            notes.append('هیستوگرام MACD در ۵ و ۱۵ دقیقه منفی است')

        # volume thrust
        if m5.vol_ratio >= 1.5:
            score += 15 if score >= 0 else -15
            notes.append(f'افزایش محسوس حجم ({m5.vol_ratio:.1f} برابر میانگین)')

        res.signal = 'BUY' if score >= 25 else 'SELL' if score <= -25 else 'WAIT'
        res.strength = min(100.0, abs(score))
        res.explanation_fa = '. '.join(notes) if notes else 'مومنتوم مشخصی وجود ندارد'
        res.supporting = {
            'rsi_5m': round(m5.rsi, 1),
            'macd_hist_5m': round(m5.macd_hist, 6),
            'macd_hist_15m': round(m15.macd_hist, 6),
            'vol_ratio': round(m5.vol_ratio, 2),
            'score': round(score, 1),
        }
        return res
