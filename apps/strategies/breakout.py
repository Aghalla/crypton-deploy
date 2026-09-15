"""Breakout: resistance/support break + candle + volume confirmation."""
import numpy as np

from apps.strategies.base import BaseStrategy, StrategyResult


class BreakoutStrategy(BaseStrategy):
    name = 'breakout'
    name_fa = 'شکست سطح'

    def evaluate(self, mtf, df_5m=None) -> StrategyResult:
        res = StrategyResult(name=self.name, name_fa=self.name_fa)
        m5 = mtf.snapshot('5m')
        structure = m5.structure
        if structure is None or df_5m is None or len(df_5m) < 30:
            res.explanation_fa = 'داده کافی برای تشخیص شکست وجود ندارد'
            return res

        price = m5.price
        score = 0.0
        notes = []
        last_candle = df_5m.iloc[-1]
        body = abs(float(last_candle['close']) - float(last_candle['open']))
        candle_bull = float(last_candle['close']) > float(last_candle['open'])

        resistances = structure.resistance_levels
        supports = structure.support_levels
        vol_ok = m5.vol_ratio >= 1.2

        # bullish breakout: close above nearest resistance
        if resistances and price > resistances[-1]:
            score += 35
            notes.append(f'قیمت از مقاومت {resistances[-1]:.8g} عبور کرد')
            if candle_bull:
                score += 15
                notes.append('کندل تأیید صعودی')
            if vol_ok:
                score += 20
                notes.append(f'حجم معاملات بالاست ({m5.vol_ratio:.1f} برابر میانگین)')
            else:
                score -= 10
                notes.append('اما حجم برای تأیید شکست کافی نیست')

        # bearish breakdown
        if supports and price < supports[-1]:
            score -= 35
            notes.append(f'قیمت از حمایت {supports[-1]:.8g} پایین‌تر رفت')
            if not candle_bull:
                score -= 15
                notes.append('کندل تأیید نزولی')
            if vol_ok:
                score -= 20
                notes.append('حجم معاملات بالاست')

        # squeeze anticipation: narrow Bollinger bandwidth
        if not notes:
            try:
                from apps.analysis.engine.indicators import bollinger
                _, _, _, bw = bollinger(df_5m['close'])
                if np.isfinite(bw.iloc[-1]) and bw.iloc[-1] < 0.02:
                    notes.append('فشردگی باند بولینگر — احتمال شکست نزدیک است، هنوز جهت مشخص نیست')
            except Exception:
                pass

        res.signal = 'BUY' if score >= 30 else 'SELL' if score <= -30 else 'WAIT'
        res.strength = min(100.0, abs(score))
        res.explanation_fa = '. '.join(notes) if notes else 'شرایط شکست سطح فراهم نیست'
        res.supporting = {
            'nearest_resistance': resistances[-1] if resistances else None,
            'nearest_support': supports[-1] if supports else None,
            'vol_ratio': round(m5.vol_ratio, 2),
            'score': round(score, 1),
        }
        return res
