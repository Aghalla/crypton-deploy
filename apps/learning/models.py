from django.db import models


class TrainingSample(models.Model):
    """One labeled example: market features at signal time -> was it correct?"""

    coin = models.ForeignKey('market_data.Coin', on_delete=models.CASCADE,
                             related_name='training_samples')
    signal = models.ForeignKey('signals.Signal', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='samples')
    created_at = models.DateTimeField()
    features = models.JSONField()
    label = models.BooleanField(null=True)      # True = TP hit before SL
    source = models.CharField(max_length=10)    # 'history' | 'live'
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class ModelMetadata(models.Model):
    """State of the latest trained model."""

    model_file = models.CharField(max_length=255)
    trained_at = models.DateTimeField(auto_now=True)
    n_samples = models.PositiveIntegerField(default=0)
    cv_accuracy = models.FloatField(default=0.0)
    feature_names = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-version']
