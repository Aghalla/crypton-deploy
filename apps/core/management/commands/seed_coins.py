"""Seed the five supported coins."""
from django.core.management.base import BaseCommand
from apps.market_data.models import Coin

COINS = [
    ('BTCUSDT', 'بیت‌کوین', 'BTC'),
    ('ETHUSDT', 'اتریوم', 'ETH'),
    ('BNBUSDT', 'بایننس کوین', 'BNB'),
    ('LINKUSDT', 'چین‌لینک', 'LINK'),
    ('SOLUSDT', 'سولانا', 'SOL'),
]


class Command(BaseCommand):
    help = 'Create the initial set of supported coins.'

    def handle(self, *args, **options):
        for order, (symbol, name, base) in enumerate(COINS):
            coin, created = Coin.objects.update_or_create(
                symbol=symbol,
                defaults={'name': name, 'base_asset': base,
                          'display_order': order, 'is_active': True})
            self.stdout.write(f'{"created" if created else "updated"} {coin}')
