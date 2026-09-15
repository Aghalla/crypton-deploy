"""Trend Following: EMA alignment + market structure + trend direction."""
from apps.strategies.base import BaseStrategy, StrategyResult


class TrendFollowingStrategy(BaseStrategy):
    name = 'trend_following'
    name_fa = 'روندگیری'

    def evaluate(self, mtf) -> StrategyResult:
        res = StrategyResult(name=self.name, name_fa=self.name_fa)
        h1 = mtf.snapshot('1h')
        m30 = mtf.snapshot('30m')
        m5 = mtf.snapshot('5m')

        score = 0.0
        notes = []
        # main trend (1h) carries the most weight
        if h1.trend == 'up':
            score += 30 + 0.3 * h1.trend_strength
            notes.append('روند ۱ ساعته صعودی است')
        elif h1.trend == 'down':
            score -= 30 + 0.3 * h1.trend_strength
            notes.append('روند ۱ ساعته نزولی است')

        if h1.ema_bias == 'bullish':
            score += 20
            notes.append('EMAها در تایم ۱ ساعته چیدمان صعودی دارند')
        elif h1.ema_bias == 'bearish':
            score -= 20
            notes.append('EMAها در تایم ۱ ساعته چیدمان نزولی دارند')

        # multi-TF EMA agreement: structure detection lags behind EMAs, so a
        # consistent bearish/bullish EMA alignment across timeframes is treated
        # as trend evidence even before swing structure flips
        if h1.ema_bias == 'bearish' and m30.ema_bias == 'bearish' and h1.trend != 'up':
            score -= 15
            notes.append('چیدمان نزولی EMAها در چند تایم‌فریم هم‌زمان است')
        elif h1.ema_bias == 'bullish' and m30.ema_bias == 'bullish' and h1.trend != 'down':
            score += 15
            notes.append('چیدمان صعودی EMAها در چند تایم‌فریم هم‌زمان است')

        # 30m confirmation
        if m30.trend == h1.trend and h1.trend != 'sideways':
            score += 15 if h1.trend == 'up' else -15
            notes.append('تایم ۳۰ دقیقه روند ۱ ساعته را تأیید می‌کند')

        # 5m pullback inside trend
        if h1.trend == 'up' and m5.rsi < 45:
            score += 10
            notes.append('اصلاح کوتاه در روند صعودی (فرصت ورود)')
        if h1.trend == 'down' and m5.rsi > 55:
            score -= 10
            notes.append('اصلاح کوتاه در روند نزولی')

        if h1.structure and h1.structure.choch:
            score *= 0.6
            notes.append('تغییر کاراکتر قیمت، ریسک برگشت روند')

        res.signal = 'BUY' if score >= 25 else 'SELL' if score <= -25 else 'WAIT'
        res.strength = min(100.0, abs(score))
        res.explanation_fa = '. '.join(notes) if notes else 'روند مشخصی شناسایی نشد'
        res.supporting = {
            'h1_trend': h1.trend,
            'h1_strength': round(h1.trend_strength, 1),
            'h1_ema_bias': h1.ema_bias,
            'm30_trend': m30.trend,
            'score': round(score, 1),
        }
        return res
