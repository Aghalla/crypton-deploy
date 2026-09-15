"""
Telegram Bot integration for Crypton trading signals.

Sends real-time signals (BUY/SELL) and system status to a Telegram chat.

Configuration (in .env):
    TELEGRAM_BOT_TOKEN  — Bot token from @BotFather
    TELEGRAM_CHAT_ID    — Target chat/group ID
    TELEGRAM_ENABLED    — 1 to enable, 0 to disable (default 1)
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger('crypton.telegram')


def _is_enabled():
    return getattr(settings, 'TELEGRAM_ENABLED', True)


def _get_token():
    return getattr(settings, 'TELEGRAM_BOT_TOKEN', '')


def _get_chat_id():
    return getattr(settings, 'TELEGRAM_CHAT_ID', '')


def send_message(text: str, parse_mode: str = 'HTML') -> bool:
    """Send a text message to the configured Telegram chat."""
    if not _is_enabled():
        return False
    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        logger.debug('Telegram not configured — skipping message')
        return False
    try:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        resp = requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True,
        }, timeout=10)
        if resp.status_code == 200 and resp.json().get('ok'):
            return True
        logger.warning('Telegram API error: %s', resp.text[:200])
        return False
    except Exception as e:
        logger.warning('Telegram send failed: %s', e)
        return False


def send_signal(signal) -> bool:
    """Format and send a new trading signal to Telegram."""
    if not _is_enabled() or not signal.is_actionable:
        return False

    from apps.signals.models import SIGNAL_LABELS

    coin_name = signal.coin.base_asset.replace('USDT', '')
    label = SIGNAL_LABELS.get(signal.signal_type, signal.signal_type)
    is_long = signal.direction == 'LONG'
    arrow = '🟢' if is_long else '🔴'
    direction_fa = 'خرید' if is_long else 'فروش'

    text = (
        f"{arrow} <b>{coin_name}/USDT — {label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 ورود: <code>{signal.entry:.2f}</code>\n"
        f"🛑 حد ضرر: <code>{signal.stop_loss:.2f}</code>\n"
        f"🎯 حد سود: <code>{signal.take_profit:.2f}</code>\n"
        f"⚖️ ریسک/بازده: {signal.risk_reward}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 قیمت: <code>{signal.price:.2f}</code>\n"
        f"🤖 اعتماد AI: <b>{signal.confidence:.0f}٪</b>\n"
        f"📊 ریسک: {signal.risk_level}\n"
    )

    # include brief explanation
    explanation = signal.explanation or {}
    selection = explanation.get('selection_reason', '')
    if selection:
        text += f"\n📌 {selection}"

    # regime
    regime = explanation.get('regime_data', {})
    if regime:
        regime_fa = {'trending': '📈 رونددار', 'range': '📊 محدوده‌ای',
                     'volatile': '⚡ پرنوسان', 'quiet': '😴 کم‌نوسان'}
        r = regime.get('regime', '')
        d = regime.get('direction', '')
        text += f"\n🌍 بازار: {regime_fa.get(r, r)} {d}"

    logger.info('sending signal to telegram: %s %s', coin_name, label)
    return send_message(text)
