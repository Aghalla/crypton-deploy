"""
AI Explanation Layer: generates a human-readable explanation of the
signal decision, including reason, positive/negative factors, risks,
and confidence breakdown. Output is in Persian.
"""
from dataclasses import dataclass, field


@dataclass
class ExplanationResult:
    reason_fa: str = ''
    positives: list = field(default_factory=list)
    negatives: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    confidence_reason_fa: str = ''
    best_strategy_fa: str = ''
    regime_fa: str = ''
    conclusion_fa: str = ''

    def to_dict(self):
        return {
            'reason': self.reason_fa,
            'positives': self.positives,
            'negatives': self.negatives,
            'risks': self.risks,
            'confidence_reason': self.confidence_reason_fa,
            'best_strategy': self.best_strategy_fa,
            'regime': self.regime_fa,
            'conclusion': self.conclusion_fa,
        }


def generate_explanation(mtf, strategy_results, confidence, regime,
                         signal_type: str, direction: str, atr_pct: float) -> ExplanationResult:
    """
    Build a structured human explanation from all analysis components.
    """
    exp = ExplanationResult()

    # --- Regime context ---
    if regime and regime.summary_fa:
        exp.regime_fa = regime.summary_fa
        exp.positives.append(f'بازار {regime.regime} با روند {regime.direction}')

    # --- Multi-timeframe reasons ---
    h1 = mtf.snapshot('1h')
    m5 = mtf.snapshot('5m')

    if h1.trend == 'up':
        exp.positives.append('روند ۱ ساعته صعودی است')
    elif h1.trend == 'down':
        exp.negatives.append('روند ۱ ساعته نزولی است')
    else:
        exp.negatives.append('روند ۱ ساعته خنثی است')

    if h1.ema_bias == 'bullish':
        exp.positives.append('چیدمان EMA در تایم ۱ ساعته صعودی است')
    elif h1.ema_bias == 'bearish':
        exp.negatives.append('چیدمان EMA در تایم ۱ ساعته نزولی است')

    if mtf.alignment > 40:
        exp.positives.append('هم‌راستایی تایم‌فریم‌ها صعودی است')
    elif mtf.alignment < -40:
        exp.positives.append('هم‌راستایی تایم‌فریم‌ها نزولی است')
    else:
        exp.negatives.append('هم‌راستایی تایم‌فریم‌ها ضعیف است')

    # --- Strategy results ---
    buy_strategies = [r for r in strategy_results if r.signal == 'BUY']
    sell_strategies = [r for r in strategy_results if r.signal == 'SELL']
    active = [r for r in strategy_results if r.signal in ('BUY', 'SELL')]

    if buy_strategies:
        names = '، '.join(r.name_fa for r in buy_strategies)
        exp.positives.append(f'{len(buy_strategies)} استراتژی خرید فعال: {names}')
    if sell_strategies:
        names = '، '.join(r.name_fa for r in sell_strategies)
        exp.negatives.append(f'{len(sell_strategies)} استراتژی فروش فعال: {names}')

    # best strategy
    if strategy_results:
        best = max(strategy_results, key=lambda r: r.strength if r.signal != 'WAIT' else 0)
        if best.signal != 'WAIT':
            exp.best_strategy_fa = f'{best.name_fa} (قدرت {best.strength:.0f}٪)'

    # --- Volume ---
    if m5.vol_ratio >= 1.2:
        exp.positives.append(f'حجم معاملات بالاست ({m5.vol_ratio:.1f} برابر میانگین)')
    elif m5.vol_ratio < 0.7:
        exp.negatives.append(f'حجم معاملات پایین است ({m5.vol_ratio:.1f} برابر میانگین)')

    # --- RSI ---
    if m5.rsi > 70:
        exp.risks.append(f'RSI در ناحیه اشباع خرید ({m5.rsi:.0f}) — احتمال اصلاح')
    elif m5.rsi < 30:
        exp.risks.append(f'RSI در ناحیه اشباع فروش ({m5.rsi:.0f}) — احتمال بازگشت')

    # --- MACD ---
    if m5.macd_hist > 0:
        exp.positives.append('هیستوگرام MACD مثبت است')
    else:
        exp.negatives.append('هیستوگرام MACD منفی است')

    # --- Volatility ---
    if atr_pct > 0.02:
        exp.risks.append(f'نوسان بازار بالاست (ATR ≈ {atr_pct:.1%})')
    elif atr_pct < 0.003:
        exp.negatives.append(f'نوسان بازار بسیار کم است (ATR ≈ {atr_pct:.2%})')

    # --- Confidence explanation ---
    score = confidence.score
    if score >= 85:
        exp.confidence_reason_fa = f'امتیاز اعتماد {score:.0f} از ۱۰۰ — تقریباً همه فاکتورها تأیید هستند'
    elif score >= 70:
        exp.confidence_reason_fa = f'امتیاز اعتماد {score:.0f} از ۱۰۰ — اکثر فاکتورها تأیید هستند'
    elif score >= 55:
        exp.confidence_reason_fa = f'امتیاز اعتماد {score:.0f} از ۱۰۰ — برخی فاکتورها تأیید و برخی مخالف هستند'
    else:
        exp.confidence_reason_fa = f'امتیاز اعتماد {score:.0f} از ۱۰۰ — فاکتورهای کافی برای تصمیم‌گیری وجود ندارد'

    # --- Reason ---
    dir_fa = 'خرید' if direction == 'LONG' else 'فروش' if direction == 'SHORT' else 'صبر'
    signal_names = {
        'BUY_STRONG': 'خرید قوی', 'BUY_MEDIUM': 'خرید متوسط', 'BUY_WEAK': 'خرید ضعیف',
        'SELL_STRONG': 'فروش قوی', 'SELL_MEDIUM': 'فروش متوسط', 'SELL_WEAK': 'فروش ضعیف',
        'WAIT': 'صبر',
    }
    signal_name = signal_names.get(signal_type, signal_type)

    if signal_type != 'WAIT':
        exp.reason_fa = (
            f'سیگنال {signal_name} صادر شد. '
            f'{mtf.summary_fa}'
        )
    else:
        exp.reason_fa = (
            f'شرایط برای ورود فراهم نیست. {mtf.summary_fa}'
        )

    # --- Conclusion ---
    if signal_type != 'WAIT':
        pos_count = len(exp.positives)
        neg_count = len(exp.negatives)
        risk_count = len(exp.risks)
        if pos_count > neg_count and risk_count <= 1:
            exp.conclusion_fa = f'به دلیل {pos_count} عامل مثبت و {neg_count} عامل منفی، سیگنال {signal_name} صادر شد.'
        elif risk_count > 1:
            exp.conclusion_fa = f'علی‌رغم وجود {risk_count} ریسک، به دلیل تأیید تایم‌فریم‌ها سیگنال {signal_name} صادر شد. با احتیاط عمل کنید.'
        else:
            exp.conclusion_fa = f'سیگنال {signal_name} با احتیاط صادر شد — {pos_count} عامل مثبت، {neg_count} عامل منفی.'
    else:
        exp.conclusion_fa = 'صبر کنید تا شرایط ورود مناسب مجدد فراهم شود.'

    return exp
