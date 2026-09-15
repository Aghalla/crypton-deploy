"""Pullback Entry: trend correction to support/EMA + entry confirmation."""
from apps.strategies.base import BaseStrategy, StrategyResult


class PullbackStrategy(BaseStrategy):
    name = 'pullback'
    name_fa = 'ورود در اصلاح'

    def evaluate(self, mtf) -> StrategyResult:
        res = StrategyResult(name=self.name, name_fa=self.name_fa)
        h1 = mtf.snapshot('1h')
        m15 = mtf.snapshot('15m')
        m5 = mtf.snapshot('5m')

        score = 0.0
        notes = []

        if h1.trend == 'up':
            # look for a pullback toward support / ema20 in 15m
            near_support = m15.structure and m15.structure.support_levels and \
                m15.price <= m15.structure.support_levels[-1] * 1.004
            rsi_dipped = m5.rsi < 45
            turning_up = m5.macd_hist > 0 and m5.trend != 'down'
            if near_support or rsi_dipped:
                score += 30
                notes.append('در روند صعودی، قیمت به ناحیه حمایت/اشباع فروش اصلاح کرده')
                if turning_up:
                    score += 25
                    notes.append('واکنش صعودی از ناحیه اصلاح تأیید شد')
                else:
                    notes.append('هنوز تأیید واکنش در ۵ دقیقه دیده نشده')
            else:
                notes.append('اصلاح مناسبی برای ورود در روند صعودی وجود ندارد')

        elif h1.trend == 'down':
            near_resistance = m15.structure and m15.structure.resistance_levels and \
                m15.price >= m15.structure.resistance_levels[0] * 0.996
            rsi_spiked = m5.rsi > 55
            turning_down = m5.macd_hist < 0 and m5.trend != 'up'
            if near_resistance or rsi_spiked:
                score -= 30
                notes.append('در روند نزولی، قیمت به ناحیه مقاومت/اشباع خرید اصلاح کرده')
                if turning_down:
                    score -= 25
                    notes.append('واکنش نزولی از ناحیه اصلاح تأیید شد')
            else:
                notes.append('اصلاح مناسبی برای ورود فروش در روند نزولی وجود ندارد')
        else:
            notes.append('روند ۱ ساعته خنثی است؛ استراتژی ورود در اصلاح فعال نیست')

        res.signal = 'BUY' if score >= 30 else 'SELL' if score <= -30 else 'WAIT'
        res.strength = min(100.0, abs(score))
        res.explanation_fa = '. '.join(notes)
        res.supporting = {
            'h1_trend': h1.trend,
            'm15_near_support': bool(m15.structure and m15.structure.support_levels),
            'm5_rsi': round(m5.rsi, 1),
            'score': round(score, 1),
        }
        return res
