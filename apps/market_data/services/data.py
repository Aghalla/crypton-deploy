"""Data service: keeps candles in the database, prices in memory only."""
import logging
from datetime import datetime, timezone

import pandas as pd

from django.conf import settings

from apps.market_data.models import Candle, Coin
from apps.market_data.services.binance import DemoMarketClient, BinanceClient, get_market_client
from apps.market_data.timeframes import ALL_TIMEFRAMES

logger = logging.getLogger('crypton.market_data')

# In-memory price cache: {symbol: {'price': float, 'change': float, 'updated_at': datetime}}
_price_cache = {}
# Latest multi-timeframe bias per symbol ('bullish'/'bearish'/'neutral'),
# refreshed by every analysis cycle — fresher than the stored signal's trend
_mtf_bias_cache = {}
# Latest regime string per symbol ('trending'/'range'/'volatile'/'quiet'),
# refreshed by every analysis cycle for the dashboard
_regime_cache = {}


def set_mtf_bias(symbol: str, bias: str):
    _mtf_bias_cache[symbol] = bias


def get_mtf_bias(symbol: str):
    return _mtf_bias_cache.get(symbol)


def set_regime(symbol: str, regime: str):
    _regime_cache[symbol] = regime


def get_regime(symbol: str):
    return _regime_cache.get(symbol)


def get_coins():
    return Coin.objects.filter(is_active=True).order_by('display_order')


def get_coin_by_base_asset(base_asset: str):
    return Coin.objects.filter(base_asset__iexact=base_asset, is_active=True).first()


def update_prices():
    """Refresh prices in memory only (no database writes)."""
    global _price_cache
    client = get_market_client()
    try:
        prices = client.get_ticker_prices()
    except Exception:
        logger.exception('failed to fetch ticker prices; falling back to demo client')
        client = DemoMarketClient()
        prices = client.get_ticker_prices()
    now = datetime.now(timezone.utc)
    for coin in get_coins():
        price = prices.get(coin.symbol)
        if price is None:
            continue
        old = _price_cache.get(coin.symbol, {})
        change = old.get('change', 0.0)
        try:
            change = client.get_24h_change(coin.symbol)
        except Exception:
            pass
        _price_cache[coin.symbol] = {
            'price': price,
            'change': change,
            'updated_at': now,
        }
    return prices


def get_price_cache():
    """Return the in-memory price cache."""
    return _price_cache


def update_candles(coin: Coin, timeframe: str, limit: int = 300):
    """Upsert the most recent candles of one timeframe for a coin."""
    client = get_market_client()
    try:
        klines = client.get_klines(coin.symbol, timeframe, limit=limit)
    except Exception:
        logger.exception('failed to fetch klines for %s %s', coin.symbol, timeframe)
        return 0
    rows = [Candle(
        coin=coin,
        timeframe=timeframe,
        open_time=k['open_time'],
        open=k['open'],
        high=k['high'],
        low=k['low'],
        close=k['close'],
        volume=k['volume'],
    ) for k in klines]
    # Insert new candles; then update existing ones that have changed
    Candle.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)
    # Update candles whose OHLCV may have changed (e.g. current incomplete candle)
    existing = {}
    for c in Candle.objects.filter(coin=coin, timeframe=timeframe,
                                   open_time__in=[r.open_time for r in rows]):
        existing[c.open_time] = c
    to_update = []
    for r in rows:
        old = existing.get(r.open_time)
        if old and (old.open != r.open or old.high != r.high or
                    old.low != r.low or old.close != r.close or
                    old.volume != r.volume):
            old.open, old.high, old.low, old.close, old.volume = (
                r.open, r.high, r.low, r.close, r.volume)
            to_update.append(old)
    if to_update:
        Candle.objects.bulk_update(to_update, ['open', 'high', 'low', 'close', 'volume'],
                                   batch_size=500)
    return len(rows)


def update_all_candles(limit=300):
    """Refresh every timeframe of every active coin."""
    for coin in get_coins():
        for tf in ALL_TIMEFRAMES:
            update_candles(coin, tf, limit=limit)


def get_candles_df(coin: Coin, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Return the stored candles as a DataFrame indexed by open_time (UTC)."""
    qs = (Candle.objects
          .filter(coin=coin, timeframe=timeframe)
          .order_by('-open_time')[:limit])
    rows = list(reversed(qs.values('open_time', 'open', 'high', 'low', 'close', 'volume')))
    if not rows:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    df = pd.DataFrame(rows)
    df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
    df = df.set_index('open_time').astype(float)
    return df


def backfill_history(coin: Coin, timeframe: str, days: int):
    """Download ~`days` of candle history for a coin into the database."""
    client = get_market_client()
    tf_delta = pd.Timedelta(minutes={'5m': 5, '15m': 15, '30m': 30, '1h': 60}[timeframe])
    end = datetime.now(tz=timezone.utc)
    start_target = end - pd.Timedelta(days=days)
    total = 0
    # Binance caps klines at 1000 per request; walk backwards in 900-candle chunks.
    chunk = 900
    end_time = end
    while True:
        try:
            klines = client.get_klines(coin.symbol, timeframe, limit=chunk, end_time=end_time)
        except Exception:
            logger.exception('history fetch failed for %s %s', coin.symbol, timeframe)
            break
        if not klines:
            break
        rows = [Candle(
            coin=coin,
            timeframe=timeframe,
            open_time=k['open_time'],
            open=k['open'],
            high=k['high'],
            low=k['low'],
            close=k['close'],
            volume=k['volume'],
        ) for k in klines]
        Candle.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)
        total += len(rows)
        oldest = klines[0]['open_time'].replace(tzinfo=timezone.utc)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        if oldest <= start_target or len(klines) < chunk:
            break
        end_time = oldest - tf_delta.to_pytimedelta()
    return total
