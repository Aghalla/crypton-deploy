from django.db import models


class Notification(models.Model):
    LEVELS = [('info', 'اطلاع'), ('success', 'موفق'), ('warning', 'هشدار'), ('error', 'خطا')]

    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    level = models.CharField(max_length=10, choices=LEVELS, default='info')
    coin = models.ForeignKey('market_data.Coin', on_delete=models.SET_NULL,
                             null=True, blank=True)
    sound = models.BooleanField(default=False)     # request a sound alert in the UI
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
