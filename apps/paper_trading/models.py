from django.db import models


class PaperTrade(models.Model):
    STATUS_OPEN = 'open'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [(STATUS_OPEN, 'باز'), (STATUS_CLOSED, 'بسته‌شده')]

    signal = models.OneToOneField('signals.Signal', on_delete=models.CASCADE,
                                  related_name='paper_trade')
    coin = models.ForeignKey('market_data.Coin', on_delete=models.CASCADE,
                             related_name='paper_trades')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    direction = models.CharField(max_length=5)     # LONG / SHORT
    entry_price = models.FloatField()
    exit_price = models.FloatField(null=True, blank=True)
    stop_loss = models.FloatField()
    take_profit = models.FloatField()
    result = models.CharField(max_length=10, blank=True)   # tp / sl / timeout
    pnl_percent = models.FloatField(null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']

    def __str__(self):
        return f'{self.coin.symbol} {self.direction} {self.opened_at:%m-%d %H:%M}'
