"""Range Trading: sideways market, react at range extremes."""
from apps.strategies.base import BaseStrategy, StrategyResult


class RangeStrategy(BaseStrategy):
    name = 'range'
    name_fa = 'معامله در محدوده'

    def evaluate(self, mtf) -> StrategyResult:
        res = StrategyResult(name=self.name, name_fa=self.name_fa)
        h1 = mtf.snapshot('1h')
        m15 = mtf.snapshot('15m')

        score = 0.0
        notes = []
        structure = m15.structure

        if h1.trend != 'sideways' or structure is None:
            notes.append('بازار روند دارد؛ شرایط معامله در محدوده مناسب نیست')
            res.explanation_fa = '. '.join(notes)
            return res

        supports = structure.support_levels
        resistances = structure.resistance_levels
        price = m15.price

        if supports and resistances:
            floor, ceiling = supports[0], resistances[-1]
            width = ceiling - floor
            if width <= 0:
                notes.append('محدوده قابل معامله‌ای شناسایی نشد')
            else:
                position = (price - floor) / width   # 0 = at floor, 1 = at ceiling
                notes.append(f'بازار در محدوده {floor:.8g} تا {ceiling:.8g} نوسان می‌کند')
                if position <= 0.25:
                    score += 35
                    notes.append('قیمت نزدیک کف محدوده است — واکنش صعودی محتمل')
                elif position >= 0.75:
                    score -= 35
                    notes.append('قیمت نزدیک سقف محدوده است — واکنش نزولی محتمل')
                else:
                    notes.append('قیمت در میانه محدوده است؛ نقطه ورود مناسب نیست')
        else:
            notes.append('سطوح کافی برای رسم محدوده وجود ندارد')

        res.signal = 'BUY' if score >= 30 else 'SELL' if score <= -30 else 'WAIT'
        res.strength = min(100.0, abs(score))
        res.explanation_fa = '. '.join(notes)
        res.supporting = {
            'h1_trend': h1.trend,
            'range_low': supports[0] if supports else None,
            'range_high': resistances[-1] if resistances else None,
            'score': round(score, 1),
        }
        return res
