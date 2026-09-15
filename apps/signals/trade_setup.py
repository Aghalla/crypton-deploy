"""
Trade Setup: dynamic entry / stop loss / take profit using ATR,
support-resistance structure, risk/reward rules, and signal strength scaling.
"""
from dataclasses import dataclass


@dataclass
class TradeSetup:
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    holding_time_minutes: int = 0
    explanation_fa: str = ''


def _strength_scale(signal_type: str) -> tuple:
    """Return (sl_multiplier, min_rr, label) based on signal strength."""
    if signal_type and 'STRONG' in signal_type:
        return 2.0, 2.0, 'قوی'
    if signal_type and 'MEDIUM' in signal_type:
        return 1.5, 1.75, 'متوسط'
    return 1.0, 1.5, 'ضعیف'


def build_trade_setup(direction: str, price: float, atr: float,
                      structure=None, signal_type: str = '') -> TradeSetup:
    """
    direction: LONG / SHORT
    structure: StructureResult of the entry timeframe (5m), may be None.
    signal_type: e.g. BUY_STRONG, SELL_WEAK — controls SL/TP tightness.
    """
    setup = TradeSetup(entry=price)
    if direction not in ('LONG', 'SHORT') or atr <= 0 or price <= 0:
        setup.explanation_fa = 'امکان محاسبه نقاط ورود/خروج وجود ندارد'
        return setup

    sl_mult, min_rr, strength_label = _strength_scale(signal_type)

    # --- SL distance ---
    sl_atr = sl_mult * atr
    swing = None
    if structure is not None:
        if direction == 'LONG' and structure.support_levels:
            swing = price - structure.support_levels[-1]   # nearest support
        elif direction == 'SHORT' and structure.resistance_levels:
            # nearest resistance = first element (list is ascending)
            swing = structure.resistance_levels[0] - price

    if swing is not None and 0.3 * sl_atr < swing < 2.0 * sl_atr:
        sl_dist = swing
        sl_basis = 'نزدیک‌ترین سطح حمایتی/مقاومتی'
    else:
        sl_dist = sl_atr
        sl_basis = f'{sl_mult}× ATR'

    if direction == 'LONG':
        setup.stop_loss = price - sl_dist
    else:
        setup.stop_loss = price + sl_dist

    # --- TP: target min_rr × SL distance from ENTRY, optionally extend to structure ---
    rr = min_rr
    tp = price + rr * sl_dist * (1 if direction == 'LONG' else -1)

    if structure is not None:
        if direction == 'LONG' and structure.resistance_levels:
            target = structure.resistance_levels[-1]
            r = (target - price) / sl_dist
            if min_rr <= r <= 3.0:
                tp, rr = target, r
        elif direction == 'SHORT' and structure.support_levels:
            target = structure.support_levels[-1]
            r = (price - target) / sl_dist
            if min_rr <= r <= 3.0:
                tp, rr = target, r

    setup.take_profit = tp
    setup.risk_reward = round(rr, 2)

    # expected holding time scales with SL distance
    setup.holding_time_minutes = int(min(150, max(20, sl_dist / atr * 40)))

    setup.explanation_fa = (
        f'حد ضرر ({strength_label}) بر اساس {sl_basis} '
        f'در {setup.stop_loss:.8g} '
        f'و حد سود در {setup.take_profit:.8g} '
        f'تعیین شد (نسبت ریسک به بازده {setup.risk_reward}). '
        f'مدت نگهداری مورد انتظار حدود {setup.holding_time_minutes} دقیقه.'
    )
    return setup
