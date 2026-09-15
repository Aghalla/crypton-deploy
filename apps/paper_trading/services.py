"""Paper trading service: simulated trades used to feed the AI learning loop."""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.paper_trading.models import PaperTrade

logger = logging.getLogger('crypton.paper')


def open_paper_trade(signal) -> PaperTrade | None:
    if not settings.PAPER_TRADE_ENABLED:
        return None
    if not signal.is_actionable or signal.direction == 'FLAT':
        return None
    trade, created = PaperTrade.objects.get_or_create(
        signal=signal,
        defaults={
            'coin': signal.coin,
            'direction': signal.direction,
            'entry_price': signal.entry,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
        })
    if created:
        logger.info('paper trade opened for %s %s', signal.coin.symbol, signal.direction)
    return trade


def close_paper_trade(trade: PaperTrade, price: float, result: str):
    long_trade = trade.direction == 'LONG'
    pnl = (price - trade.entry_price) / trade.entry_price * (1 if long_trade else -1) * 100
    trade.status = PaperTrade.STATUS_CLOSED
    trade.exit_price = price
    trade.result = result
    trade.pnl_percent = round(pnl, 3)
    trade.closed_at = timezone.now()
    trade.duration_minutes = int((trade.closed_at - trade.opened_at).total_seconds() // 60)
    trade.save()
    logger.info('paper trade closed: %s %s pnl=%.2f%%',
                trade.coin.symbol, trade.result, trade.pnl_percent)


def monitor_paper_trades():
    """Check open paper trades against the latest price and candle high/low."""
    from apps.market_data.services.data import get_price_cache
    now = timezone.now()
    for trade in PaperTrade.objects.filter(status=PaperTrade.STATUS_OPEN) \
            .select_related('coin'):
        cached = get_price_cache().get(trade.coin.symbol, {})
        price = cached.get('price')
        if price is None:
            continue
        price = float(price)
        long_trade = trade.direction == 'LONG'
        # get latest 5m candle high/low
        candle_high, candle_low = price, price
        try:
            from apps.market_data.services.data import get_candles_df
            df5 = get_candles_df(trade.coin, '5m', limit=2)
            if len(df5) >= 1:
                candle_high = float(df5.iloc[-1]['high'])
                candle_low = float(df5.iloc[-1]['low'])
        except Exception:
            pass
        tp_hit = (price >= trade.take_profit or candle_high >= trade.take_profit) if long_trade \
            else (price <= trade.take_profit or candle_low <= trade.take_profit)
        sl_hit = (price <= trade.stop_loss or candle_low <= trade.stop_loss) if long_trade \
            else (price >= trade.stop_loss or candle_high >= trade.stop_loss)
        timeout = trade.opened_at + timedelta(
            minutes=trade.signal.holding_time_minutes * settings.PAPER_TRADE_TIMEOUT_FACTOR
            if trade.signal and trade.signal.holding_time_minutes
            else 24 * 60)
        if tp_hit and sl_hit:
            close_paper_trade(trade, trade.stop_loss, 'sl')
        elif tp_hit:
            close_paper_trade(trade, trade.take_profit, 'tp')
        elif sl_hit:
            close_paper_trade(trade, trade.stop_loss, 'sl')
        elif now > timeout:
            close_paper_trade(trade, price, 'timeout')
