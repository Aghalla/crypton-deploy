"""Shared timeframe helpers."""
from datetime import timedelta

TIMEFRAME_MINUTES = {
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
}

ALL_TIMEFRAMES = tuple(TIMEFRAME_MINUTES.keys())

BINANCE_INTERVALS = {
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
}


def timeframe_delta(timeframe: str) -> timedelta:
    return timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
