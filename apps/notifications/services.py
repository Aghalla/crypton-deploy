"""In-app notifications + sound alert flag for important new signals."""
import logging

from apps.notifications.models import Notification
from apps.signals.models import SIGNAL_LABELS

logger = logging.getLogger('crypton.notifications')


def notify_new_signal(signal):
    important = signal.signal_type in ('BUY_STRONG', 'SELL_STRONG',
                                       'BUY_MEDIUM', 'SELL_MEDIUM')
    Notification.objects.create(
        title=f'{signal.coin.base_asset}: {SIGNAL_LABELS.get(signal.signal_type, signal.signal_type)}',
        message=(signal.explanation or {}).get('narrative', ''),
        level='success' if signal.signal_type.startswith('BUY') else 'warning'
        if signal.signal_type.startswith('SELL') else 'info',
        coin=signal.coin,
        sound=important,
    )


def notify_signal_closed(signal):
    labels = {'tp': 'به هدف رسید (سود)', 'sl': 'به حد ضرر رسید (زیان)',
              'expired': 'منقضی شد'}
    Notification.objects.create(
        title=f'{signal.coin.base_asset}: سیگنال {labels.get(signal.status, signal.status)}',
        message=(f'نتیجه: {signal.result_pnl:+.2f}%' if signal.result_pnl is not None else ''),
        level='success' if signal.status == 'tp' else 'warning',
        coin=signal.coin,
        sound=False,
    )
