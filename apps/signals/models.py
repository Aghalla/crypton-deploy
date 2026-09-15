from django.db import models

SIGNAL_TYPES = [
    ('BUY_STRONG', 'خرید قوی'),
    ('BUY_MEDIUM', 'خرید متوسط'),
    ('BUY_WEAK', 'خرید ضعیف'),
    ('WAIT', 'صبر'),
    ('SELL_WEAK', 'فروش ضعیف'),
    ('SELL_MEDIUM', 'فروش متوسط'),
    ('SELL_STRONG', 'فروش قوی'),
]
SIGNAL_LABELS = dict(SIGNAL_TYPES)


class Signal(models.Model):
    STATUS_OPEN = 'open'
    STATUS_TP = 'tp'
    STATUS_SL = 'sl'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'باز'),
        (STATUS_TP, 'هدف (سود)'),
        (STATUS_SL, 'حد ضرر (زیان)'),
        (STATUS_EXPIRED, 'منقضی'),
    ]

    coin = models.ForeignKey('market_data.Coin', on_delete=models.CASCADE, related_name='signals')
    signal_type = models.CharField(max_length=12, choices=SIGNAL_TYPES)
    confidence = models.FloatField()                  # 0..100
    direction = models.CharField(max_length=4)        # LONG / SHORT / FLAT
    price = models.FloatField()                      # price at signal time
    entry = models.FloatField()
    stop_loss = models.FloatField()
    take_profit = models.FloatField()
    risk_reward = models.FloatField()
    holding_time_minutes = models.PositiveIntegerField()
    risk_level = models.CharField(max_length=10)      # low / medium / high
    explanation = models.JSONField(default=dict)      # AI explanation layer
    strategies = models.JSONField(default=list)       # per-strategy results snapshot
    confidence_breakdown = models.JSONField(default=dict)
    features = models.JSONField(default=dict)         # ML feature vector for learning
    ai_adjustment = models.FloatField(default=0.0)    # ML correction applied to confidence

    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_OPEN)
    result_pnl = models.FloatField(null=True, blank=True)   # percent profit/loss at close
    closed_at = models.DateTimeField(null=True, blank=True)
    trend = models.CharField(max_length=10, blank=True, default='sideways')  # up / down / sideways

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'

    def __str__(self):
        return f'{self.coin.symbol} {self.get_signal_type_display()} @{self.entry:.4f}'

    @property
    def signal_label(self):
        return SIGNAL_LABELS.get(self.signal_type, self.signal_type)

    @property
    def is_actionable(self):
        return self.signal_type != 'WAIT'

    @property
    def is_correct(self):
        return self.status == self.STATUS_TP


class StrategyPerformance(models.Model):
    """Tracks accuracy of each strategy per coin for AI-based ranking."""

    coin = models.ForeignKey('market_data.Coin', on_delete=models.CASCADE,
                             related_name='strategy_performances')
    strategy_name = models.CharField(max_length=30)   # trend_following / breakout / etc.
    strategy_fa = models.CharField(max_length=30, blank=True)
    total_predictions = models.PositiveIntegerField(default=0)
    successful_predictions = models.PositiveIntegerField(default=0)
    failed_predictions = models.PositiveIntegerField(default=0)
    accuracy_percentage = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('coin', 'strategy_name')
        ordering = ['-accuracy_percentage']

    def __str__(self):
        return f'{self.coin.base_asset} {self.strategy_fa}: {self.accuracy_percentage:.1f}%'

    @property
    def weight(self):
        """Return a multiplier 0.5..2.0 based on historical accuracy."""
        if self.total_predictions < 5:
            return 1.0
        return max(0.5, min(2.0, self.accuracy_percentage / 50.0))
