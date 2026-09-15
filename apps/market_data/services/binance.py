"""Binance REST client with proxy support and a synthetic demo fallback."""
import logging
import random
from datetime import datetime, timedelta, timezone

import requests

from django.conf import settings

from apps.market_data.timeframes import BINANCE_INTERVALS, timeframe_delta

logger = logging.getLogger('crypton.market_data')

DEFAULT_COIN_PRICES = {
    'BTCUSDT': 68000.0,
    'ETHUSDT': 3500.0,
    'BNBUSDT': 590.0,
    'LINKUSDT': 14.5,
    'SOLUSDT': 165.0,
}

KLINE_COLUMNS = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time']


class BinanceClient:
    """Thin wrapper over Binance public REST endpoints."""

    def __init__(self):
        self.base_url = settings.BINANCE_BASE_URL.rstrip('/')
        self.proxies = {'http': settings.BINANCE_PROXY, 'https': settings.BINANCE_PROXY} \
            if settings.BINANCE_PROXY else None
        self.session = requests.Session()
        if self.proxies:
            self.session.proxies.update(self.proxies)
        self._blocked = False  # set True on 451 (geo-blocked)

    def _get(self, path, params=None):
        if self._blocked:
            raise requests.exceptions.HTTPError('451 geo-blocked')
        response = self.session.get(f'{self.base_url}{path}', params=params, timeout=10)
        if response.status_code == 451:
            self._blocked = True
            logger.warning('Binance 451 — geo-blocked, switching to demo mode')
            raise requests.exceptions.HTTPError('451 Unavailable For Legal Reasons')
        response.raise_for_status()
        return response.json()

    def ping(self):
        try:
            self._get('/api/v3/ping')
            return True
        except requests.RequestException:
            return False

    def get_klines(self, symbol: str, interval: str, limit: int = 500, end_time=None):
        """Return list of dicts with open_time (UTC datetime) and OHLCV floats."""
        params = {'symbol': symbol, 'interval': BINANCE_INTERVALS[interval], 'limit': limit}
        if end_time is not None:
            params['endTime'] = int(end_time.timestamp() * 1000)
        raw = self._get('/api/v3/klines', params)
        klines = []
        for row in raw:
            klines.append({
                'open_time': datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': float(row[5]),
                'close_time': datetime.fromtimestamp(row[6] / 1000, tz=timezone.utc),
            })
        return klines

    def get_ticker_prices(self):
        """Return {symbol: price} for all symbols."""
        raw = self._get('/api/v3/ticker/price')
        return {row['symbol']: float(row['price']) for row in raw}

    def get_24h_change(self, symbol: str) -> float:
        raw = self._get('/api/v3/ticker/24hr', {'symbol': symbol})
        return float(raw.get('priceChangePercent', 0.0))


class DemoMarketClient:
    """
    Synthetic market data generator (random walk with mild trends) used when
    the Binance API is unreachable or DEMO_MODE is enabled.
    """

    def __init__(self):
        self._state = {}  # symbol -> {price, drift}
        rng = random.Random(42)
        for symbol, base in DEFAULT_COIN_PRICES.items():
            self._state[symbol] = {'price': base, 'drift': rng.uniform(-0.0004, 0.0006)}

    def _step(self, symbol: str, tf_minutes: int):
        state = self._state[symbol]
        rng = random.Random()
        vol = 0.0016 * (tf_minutes / 5) ** 0.5
        change = rng.gauss(state['drift'], vol)
        # occasionally flip the drift so the synthetic market has regime changes
        if rng.random() < 0.02:
            state['drift'] = rng.uniform(-0.0004, 0.0006)
        state['price'] = max(state['price'] * (1 + change), DEFAULT_COIN_PRICES[symbol] * 0.2)
        return state['price']

    def get_klines(self, symbol: str, interval: str, limit: int = 500, end_time=None):
        tf_delta = timeframe_delta(interval)
        tf_minutes = int(tf_delta.total_seconds() // 60)
        last_close = end_time or datetime.now(tz=timezone.utc)
        last_close = last_close.replace(second=0, microsecond=0)
        rng = random.Random(hash(symbol) & 0xffff)
        vol = 0.0016 * (tf_minutes / 5) ** 0.5
        price = self._state[symbol]['price']
        closes = [price]
        for _ in range(limit - 1):
            price = price / (1 + rng.gauss(0.0002, vol))
            closes.append(price)
        closes.reverse()
        open_time = last_close - tf_delta * (limit - 1)
        candles = []
        for i, close in enumerate(closes):
            prev = closes[i - 1] if i > 0 else close * (1 - vol)
            o = prev
            h = max(o, close) * (1 + rng.uniform(0, vol))
            l = min(o, close) * (1 - rng.uniform(0, vol))
            candles.append({
                'open_time': open_time + tf_delta * i,
                'open': o,
                'high': h,
                'low': l,
                'close': close,
                'volume': rng.uniform(50, 500),
                'close_time': open_time + tf_delta * (i + 1) - timedelta(seconds=1),
            })
        return candles

    def get_ticker_prices(self):
        return {symbol: self._step(symbol, 5) for symbol in self._state}

    def get_24h_change(self, symbol: str) -> float:
        return random.Random().uniform(-6, 6)


_binance_client = None


def get_market_client():
    """Always return the Binance client. No demo fallback."""
    global _binance_client
    if _binance_client is None:
        _binance_client = BinanceClient()
    return _binance_client
