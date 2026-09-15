"""
Confidence Engine: 0..100 score from four 25-point factors
(trend / multi-timeframe confirmation / entry quality / risk management).
"""
from dataclasses import dataclass, field


@dataclass
class ConfidenceResult:
    score: float = 0.0
    direction: str = 'FLAT'            # LONG / SHORT / FLAT
    breakdown: dict = field(default_factory=dict)
    positives: list = field(default_factory=list)
    negatives: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    narrative_fa: str = ''


def _trend_score(mtf, sign: float):
    """25 points: main-trend clarity (1h) with 30m confirmation."""
    h1, m30 = mtf.snapshot('1h'), mtf.snapshot('30m')
    pts, pos, neg = 0.0, [], []
    want = 'up' if sign > 0 else 'down'
    if h1.trend == want:
        pts += 12 + 0.13 * min(100, h1.trend_strength)
        pos.append(f'روند غالب ۱ ساعته {"صعودی" if want == "up" else "نزولی"} است')
        if m30.trend == want:
            pts += 8
            pos.append('تایم ۳۰ دقیقه روند اصلی را تأیید می‌کند')
        elif m30.trend != 'sideways':
            neg.append('تایم ۳۰ دقیقه فعلاً خلاف جهت اصلی است (اصلاح)')
    elif h1.trend == 'sideways' and h1.ema_bias == ('bullish' if sign > 0 else 'bearish'):
        # swing-structure hasn't flipped yet but EMA alignment is clear
        pts += 10
        pos.append('روند ۱ ساعته خنثی ولی چیدمان EMA یک‌سویه است')
    else:
        neg.append('روند ۱ ساعته در جهت سیگنال نیست')
    if (sign > 0 and h1.ema_bias == 'bullish') or (sign < 0 and h1.ema_bias == 'bearish'):
        pts += 5
    return min(25.0, pts), pos, neg


def _mtf_score(mtf, sign: float):
    """25 points: multi-timeframe confirmation of the signal direction."""
    pos, neg = [], []
    align = mtf.alignment * sign  # positive when confirming our side
    pts = max(0.0, align) / 100 * 25
    if align > 30:
        pos.append('هم‌راستایی تایم‌فریم‌ها جهت سیگنال را تأیید می‌کند')
    elif align < -30:
        neg.append('هم‌راستایی تایم‌فریم‌ها خلاف جهت سیگنال است')
    else:
        neg.append('هم‌راستایی تایم‌فریم‌ها ضعیف است')
    s5 = mtf.snapshot('5m')
    if s5.structure and s5.structure.choch:
        neg.append('در ۵ دقیقه تغییر کاراکتر قیمت دیده می‌شود')
        pts *= 0.7
    return min(25.0, pts), pos, neg


def _entry_quality_score(mtf, strategy_results, sign: float):
    """25 points: 5m confirmation + strategy agreement."""
    pos, neg = [], []
    m5 = mtf.snapshot('5m')
    pts = 0.0
    want_trend = 'up' if sign > 0 else 'down'
    if m5.trend == want_trend:
        pts += 6
        pos.append(f'تأیید ورود در تایم ۵ دقیقه ({"صعودی" if sign > 0 else "نزولی"})')
    else:
        neg.append('تأیید ورود در تایم ۵ دقیقه ضعیف است')
    if m5.vol_ratio >= 1.1:
        pts += 4
        pos.append('حجم معاملات ورود را تأیید می‌کند')
    elif m5.vol_ratio < 0.8:
        neg.append('حجم معاملات پایین است')

    want_signal = 'BUY' if sign > 0 else 'SELL'
    votes = [r for r in strategy_results if r.signal == want_signal]
    active = [r for r in strategy_results if r.signal in ('BUY', 'SELL')]
    if active:
        majority = len(votes) / len(active)
        pts += majority * 15
        if majority >= 0.6:
            pos.append(f'{len(votes)} استراتژی از {len(active)} استراتژی فعال هم‌جهت سیگنال‌اند')
        else:
            neg.append('توافق استراتژی‌ها بر جهت سیگنال کامل نیست')
    else:
        neg.append('هیچ استراتژی ورود فعالی ندارد')
    return min(25.0, pts), pos, neg


def _risk_score(mtf, atr_value: float, price: float):
    """25 points: volatility sanity and structural risk."""
    pos, neg, risks = [], [], []
    pts = 0.0
    if atr_value <= 0 or price <= 0:
        return 0.0, pos, neg, ['داده نوسان کافی نیست']
    atr_pct = atr_value / price
    if 0.0005 <= atr_pct <= 0.02:
        pts += 10
        pos.append(f'نوسان بازار مناسب است (ATR ≈ {atr_pct:.2%})')
    elif atr_pct > 0.02:
        pts += 4
        risks.append('نوسان بازار بالاست؛ ریسک معامله بیشتر است')
    else:
        neg.append('نوسان بازار بسیار کم است')

    h1 = mtf.snapshot('1h')
    s = h1.structure
    if s:
        if s.choch:
            risks.append('تغییر کاراکتر در ساختار ۱ ساعته — احتمال برگشت روند')
        else:
            pts += 8
        if s.bos:
            pts += 7
            pos.append('شکست ساختار جهت سیگنال را تأیید می‌کند')
    m5 = mtf.snapshot('5m')
    if m5.rsi > 75 or m5.rsi < 25:
        risks.append('اشباع در RSI پنج‌دقیقه — احتمال اصلاح کوتاه')
        pts = max(0.0, pts - 5)
    else:
        pts += 5
    return min(25.0, pts), pos, neg, risks


def compute_confidence(mtf, strategy_results, direction_hint: str) -> ConfidenceResult:
    """direction_hint: 'LONG' or 'SHORT' — the side implied by strategy majority."""
    result = ConfidenceResult()
    if direction_hint not in ('LONG', 'SHORT'):
        result.narrative_fa = 'جهت معامله مشخص نیست؛ سیگنال صبر.'
        return result

    sign = 1.0 if direction_hint == 'LONG' else -1.0
    if mtf.alignment * sign < -30:
        result.direction = 'FLAT'
        result.narrative_fa = 'تایم‌فریم‌های بالاتر خلاف جهت پیشنهادی هستند؛ صبر منطقی‌تر است.'
        result.breakdown = {'trend': 0, 'multi_timeframe': 0, 'entry_quality': 0,
                            'risk_management': 0, 'total': 0}
        return result

    t_pts, t_pos, t_neg = _trend_score(mtf, sign)
    m_pts, m_pos, m_neg = _mtf_score(mtf, sign)
    e_pts, e_pos, e_neg = _entry_quality_score(mtf, strategy_results, sign)
    m5 = mtf.snapshot('5m')
    r_pts, r_pos, r_neg, r_risks = _risk_score(mtf, m5.atr, m5.price)

    result.score = round(t_pts + m_pts + e_pts + r_pts, 1)
    result.direction = direction_hint
    result.breakdown = {
        'trend': round(t_pts, 1),
        'multi_timeframe': round(m_pts, 1),
        'entry_quality': round(e_pts, 1),
        'risk_management': round(r_pts, 1),
        'total': result.score,
    }
    result.positives = t_pos + m_pos + e_pos + r_pos
    result.negatives = t_neg + m_neg + e_neg
    result.risks = r_risks

    dir_fa = 'خرید' if direction_hint == 'LONG' else 'فروش'
    result.narrative_fa = (
        f'امتیاز اعتماد {result.score} از ۱۰۰ برای {dir_fa} محاسبه شد: '
        f'روند {t_pts:.0f}/۲۵، هم‌راستایی تایم‌فریم‌ها {m_pts:.0f}/۲۵، '
        f'کیفیت ورود {e_pts:.0f}/۲۵، مدیریت ریسک {r_pts:.0f}/۲۵.'
    )
    return result


def map_score_to_signal_type(score: float, direction: str) -> str:
    """85+: STRONG, 70-85: MEDIUM, 55-70: WEAK, otherwise WAIT."""
    if score < 55:
        return 'WAIT'
    if score >= 85:
        return 'BUY_STRONG' if direction == 'LONG' else 'SELL_STRONG'
    if score >= 70:
        return 'BUY_MEDIUM' if direction == 'LONG' else 'SELL_MEDIUM'
    return 'BUY_WEAK' if direction == 'LONG' else 'SELL_WEAK'


def risk_level_from_score(score: float, atr_pct: float) -> str:
    if score >= 75 and atr_pct < 0.015:
        return 'low'
    if score < 55 or atr_pct > 0.02:
        return 'high'
    return 'medium'
