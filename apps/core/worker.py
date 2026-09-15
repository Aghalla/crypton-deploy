"""
Background worker: price updates, candle sync, periodic analysis and
signal/paper-trade monitoring, all in daemon threads.

Run standalone with `python manage.py run_worker`, or let runserver start it
automatically via WORKER_AUTOSTART.
"""
from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

from apps.market_data.services.data import get_coins, get_price_cache, update_all_candles, update_prices
from apps.signals.engine import analyze_coin, check_open_signals, expire_stale_signals

logger = logging.getLogger('crypton.worker')

DB_LOCK_RETRIES = 3
DB_LOCK_DELAY = 2  # seconds between retries


def retry_on_db_lock(fn, retries=DB_LOCK_RETRIES, delay=DB_LOCK_DELAY):
    """Call fn(); on OperationalError 'database is locked', retry with backoff."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if 'database is locked' in str(e) and attempt < retries - 1:
                logger.warning('database locked, retry %d/%d in %ds',
                               attempt + 1, retries, delay)
                time.sleep(delay * (attempt + 1))
            else:
                raise


def broadcast_overview():
    """Push a fresh overview payload to all connected dashboard sockets."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from apps.dashboard.consumers import get_overview
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)('dashboard', {
            'type': 'overview.event',
            'payload': async_to_sync(get_overview)(),
        })
    except Exception:
        logger.exception('broadcast failed')


def broadcast_signal(signal):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        payload = {
            'coin': signal.coin.base_asset,
            'signal_label': signal.signal_label,
            'signal_type': signal.signal_type,
            'confidence': signal.confidence,
            'direction': signal.direction,
            'sound': signal.signal_type in ('BUY_STRONG', 'SELL_STRONG',
                                            'BUY_MEDIUM', 'SELL_MEDIUM'),
        }
        async_to_sync(channel_layer.group_send)('dashboard', {
            'type': 'signal.event', 'payload': payload})
    except Exception:
        logger.exception('signal broadcast failed')


# Store previous prices for sudden-change detection
_prev_prices = {}
# Sudden move threshold: 1.5% in one price_update cycle
SUDDEN_MOVE_PCT = 1.5
# Save prices to database every N minutes for AI historical analysis
PRICE_DB_SAVE_SECONDS = 300  # 5 minutes
_last_db_save = 0


def _save_prices_to_db():
    """Persist current in-memory prices to PriceTicker for AI history."""
    from apps.market_data.models import PriceTicker
    cache = get_price_cache()
    for coin in get_coins():
        data = cache.get(coin.symbol)
        if data and data.get('price'):
            PriceTicker.objects.update_or_create(
                coin=coin,
                defaults={
                    'price': data['price'],
                    'change_percent_24h': data.get('change', 0.0),
                },
            )


def price_loop(stop: threading.Event):
    global _prev_prices, _last_db_save
    while not stop.is_set():
        try:
            retry_on_db_lock(update_prices)
            broadcast_overview()
            # detect sudden price moves → trigger immediate analysis
            cache = get_price_cache()
            for symbol, data in cache.items():
                price = data.get('price')
                if price is None:
                    continue
                prev = _prev_prices.get(symbol)
                if prev and prev > 0:
                    pct_change = abs(price - prev) / prev * 100
                    if pct_change >= SUDDEN_MOVE_PCT:
                        logger.info('sudden move detected: %s %.2f%% (%.2f → %.2f)',
                                    symbol, pct_change, prev, price)
                        from apps.market_data.services.data import get_coin_by_base_asset
                        coin = get_coin_by_base_asset(symbol.replace('USDT', ''))
                        if coin:
                            try:
                                retry_on_db_lock(lambda c=coin: analyze_coin(c))
                            except Exception:
                                logger.exception('sudden-move analysis failed for %s', symbol)
                _prev_prices[symbol] = price
            # periodically save prices to DB for AI history
            now = time.time()
            if now - _last_db_save >= PRICE_DB_SAVE_SECONDS:
                try:
                    retry_on_db_lock(_save_prices_to_db)
                    _last_db_save = now
                except Exception:
                    logger.exception('failed to save prices to DB')
        except Exception:
            logger.exception('price loop error')
        stop.wait(settings.PRICE_UPDATE_SECONDS)


def candle_loop(stop: threading.Event):
    # initial sync so the dashboard has charts immediately
    try:
        retry_on_db_lock(lambda: update_all_candles(limit=300))
    except Exception:
        logger.exception('initial candle sync failed')
    while not stop.is_set():
        stop.wait(settings.CANDLE_UPDATE_SECONDS)
        try:
            retry_on_db_lock(lambda: update_all_candles(limit=60))
        except Exception:
            logger.exception('candle loop error')


def _is_5m_boundary() -> bool:
    """Check if we're within 30 seconds of a 5-minute candle boundary."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return (now.minute % 5 == 0 and now.second < 30) or \
           (now.minute % 5 == 4 and now.second >= 30)


def analysis_loop(stop: threading.Event):
    while not stop.is_set():
        started = time.time()
        try:
            retry_on_db_lock(expire_stale_signals)
            from apps.paper_trading.services import monitor_paper_trades
            for coin in get_coins():
                retry_on_db_lock(lambda c=coin: check_open_signals(c))
            # only run full analysis after a 5M candle closes
            if _is_5m_boundary():
                for coin in get_coins():
                    retry_on_db_lock(lambda c=coin: analyze_coin(c))
            retry_on_db_lock(monitor_paper_trades)
        except Exception:
            logger.exception('analysis loop error')
        elapsed = time.time() - started
        stop.wait(max(30, settings.ANALYSIS_INTERVAL_SECONDS - elapsed))


def monitor_loop(stop: threading.Event):
    while not stop.is_set():
        stop.wait(settings.MONITOR_INTERVAL_SECONDS)
        try:
            retry_on_db_lock(expire_stale_signals)
            from apps.paper_trading.services import monitor_paper_trades
            for coin in get_coins():
                retry_on_db_lock(lambda c=coin: check_open_signals(c))
            retry_on_db_lock(monitor_paper_trades)
        except Exception:
            logger.exception('monitor loop error')


LOOPS = {
    'price': price_loop,
    'candles': candle_loop,
    'analysis': analysis_loop,
    'monitor': monitor_loop,
}


def start_worker_threads() -> threading.Event:
    stop = threading.Event()
    for name, fn in LOOPS.items():
        t = threading.Thread(target=fn, args=(stop,), name=f'crypton-{name}', daemon=True)
        t.start()
        logger.info('worker thread started: %s', name)
    return stop
