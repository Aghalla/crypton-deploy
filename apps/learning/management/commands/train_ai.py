"""Initial AI training: download history, build dataset, train the model."""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.learning.dataset import build_historical_samples
from apps.learning.models import TrainingSample
from apps.learning.services import train_model
from apps.market_data.models import Coin
from apps.market_data.services.data import backfill_history
from apps.market_data.timeframes import ALL_TIMEFRAMES


class Command(BaseCommand):
    help = 'Download historical candles, build the training dataset and train the AI model.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None,
                            help='days of 5m history to download per coin')
        parser.add_argument('--skip-download', action='store_true',
                            help='reuse candles already in the database')
        parser.add_argument('--min-samples', type=int, default=200)

    def handle(self, *args, **options):
        days = options['days'] or settings.HISTORY_DAYS
        coins = Coin.objects.filter(is_active=True)

        if not options['skip_download']:
            for coin in coins:
                for tf in ALL_TIMEFRAMES:
                    limit_days = days if tf == '5m' else min(days, 10)
                    n = backfill_history(coin, tf, limit_days)
                    self.stdout.write(f'{coin.symbol} {tf}: {n} candles stored')

        total = 0
        for coin in coins:
            samples, skipped = build_historical_samples(coin)
            self.stdout.write(f'{coin.symbol}: {len(samples)} samples '
                              f'({skipped} skipped)')
            rows = [TrainingSample(
                coin=coin,
                created_at=s['created_at'],
                features=s['features'],
                label=s['label'],
                source='history',
            ) for s in samples]
            TrainingSample.objects.filter(coin=coin, source='history').delete()
            TrainingSample.objects.bulk_create(rows, batch_size=500)
            total += len(rows)

        self.stdout.write(f'total training samples: {total}')
        result = train_model(min_samples=options['min_samples'])
        self.stdout.write(str(result))
        if result.get('trained'):
            self.stdout.write(self.style.SUCCESS(
                f'model trained on {result["n_samples"]} samples '
                f'(cv accuracy {result["cv_accuracy"]:.1%})'))
        else:
            self.stdout.write(self.style.WARNING(result['reason']))
