from django.db import models


class Coin(models.Model):
    """A supported cryptocurrency pair (e.g. BTC/USDT)."""

    symbol = models.CharField(max_length=20, unique=True)   # BTCUSDT (Binance symbol)
    name = models.CharField(max_length=50)                  # بیت‌کوین
    base_asset = models.CharField(max_length=10)            # BTC
    quote_asset = models.CharField(max_length=10, default='USDT')
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'symbol']

    def __str__(self):
        return f'{self.base_asset}/{self.quote_asset}'

    @property
    def slug(self):
        return self.base_asset.lower()


class Candle(models.Model):
    """A single OHLCV candle. `open_time` is UTC."""

    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name='candles')
    timeframe = models.CharField(max_length=4)  # 5m / 15m / 30m / 1h
    open_time = models.DateTimeField(db_index=True)
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=24, decimal_places=8)

    class Meta:
        unique_together = ('coin', 'timeframe', 'open_time')
        ordering = ['open_time']
        indexes = [
            models.Index(fields=['coin', 'timeframe', 'open_time']),
        ]

    def __str__(self):
        return f'{self.coin.symbol} {self.timeframe} {self.open_time:%Y-%m-%d %H:%M}'


class PriceTicker(models.Model):
    """Latest price snapshot per coin."""

    coin = models.OneToOneField(Coin, on_delete=models.CASCADE, related_name='ticker')
    price = models.DecimalField(max_digits=20, decimal_places=8)
    change_percent_24h = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.coin.symbol} {self.price}'
