"""
Trade Setup: dynamic entry / stop loss / take profit using ATR,
support-resistance structure and risk/reward rules.
"""
from dataclasses import dataclass


@dataclass
class TradeSetup:
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    holding_time_minutes: int = 0    # expected holding time for 5m-style trades
    explanation_fa: str = ''


def build_trade_setup(direction: str, price: float, atr: float, structure) -> TradeSetup:
    """
    direction: LONG / SHORT
    structure: StructureResult of the entry timeframe (5m), may be None.
    SL: beyond the recent swing / 1.5*ATR, whichever is safer.
    TP: min 1.5R; snapped to the nearest opposing structure level when close.
    """
    setup = TradeSetup(entry=price)
    if direction not in ('LONG', 'SHORT') or atr <= 0 or price <= 0:
        setup.explanation_fa = 'امکان محاسبه نقاط ورود/خروج وجود ندارد'
        return setup

    sl_atr = 1.5 * atr
    swing = None
    if structure is not None:
        if direction == 'LONG' and structure.support_levels:
            swing = price - structure.support_levels[-1]
        elif direction == 'SHORT' and structure.resistance_levels:
            swing = structure.resistance_levels[0] - price

    if swing is not None and 0.3 * sl_atr < swing < 2.0 * sl_atr:
        sl_dist = swing
        sl_basis = 'نزدیک‌ترین سطح حمایتی/مقاومتی'
    else:
        sl_dist = sl_atr
        sl_basis = '۱.۵ برابر ATR'

    if direction == 'LONG':
        setup.stop_loss = price - sl_dist
    else:
        setup.stop_loss = price + sl_dist

    # take profit: 1.8R default, extended to structure target if reachable
    rr = 1.8
    tp = setup.stop_loss + rr * sl_dist * (1 if direction == 'LONG' else -1)
    # try improving R:R by targeting the opposing structure level
    if structure is not None:
        if direction == 'LONG' and structure.resistance_levels:
            target = structure.resistance_levels[-1]
            r = (target - price) / sl_dist
            if 1.3 <= r <= 2.6:
                tp, rr = target, r
        elif direction == 'SHORT' and structure.support_levels:
            target = structure.support_levels[-1]
            r = (price - target) / sl_dist
            if 1.3 <= r <= 2.6:
                tp, rr = target, r
    setup.take_profit = tp
    setup.risk_reward = round(rr, 2)

    # expected holding time: a typical 5m trade lasts 6-30 candles
    setup.holding_time_minutes = int(min(150, max(30, sl_dist / atr * 50)))
    setup.explanation_fa = (
        f'حد ضرر بر اساس {sl_basis} در {setup.stop_loss:.8g} و حد سود در {setup.take_profit:.8g} '
        f'تعیین شد (نسبت ریسک به بازده {setup.risk_reward}). '
        f'مدت نگهداری مورد انتظار حدود {setup.holding_time_minutes} دقیقه.'
    )
    return setup
