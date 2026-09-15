"""REST API views (JSON only)."""
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.learning.services import accuracy_stats
from apps.market_data.services.data import (get_coin_by_base_asset, get_coins,
                                            get_candles_df, get_price_cache,
                                            get_mtf_bias, get_regime,
                                            get_regime_direction,
                                            is_connected, try_reconnect)
from apps.market_data.timeframes import TIMEFRAME_MINUTES
from apps.notifications.models import Notification
from apps.signals.models import SIGNAL_LABELS, Signal, StrategyPerformance


def _last_signal_payload(coin):
    sig = Signal.objects.filter(coin=coin).first()
    trend = get_mtf_bias(coin.symbol) or (sig.trend if sig else None)
    regime = get_regime(coin.symbol) or (sig.explanation or {}).get('regime_data', {}).get('regime', '') if sig else ''
    regime_direction = get_regime_direction(coin.symbol) or trend
    if sig is None:
        return None
    return {
        'id': sig.id,
        'signal_type': sig.signal_type,
        'signal_label': SIGNAL_LABELS.get(sig.signal_type, sig.signal_type),
        'confidence': round(sig.confidence, 1),
        'risk_level': sig.risk_level,
        'direction': sig.direction,
        'trend': trend,
        'regime': regime,
        'regime_direction': regime_direction,
        'entry': sig.entry,
        'stop_loss': sig.stop_loss,
        'take_profit': sig.take_profit,
        'risk_reward': sig.risk_reward,
        'holding_time_minutes': sig.holding_time_minutes,
        'status': sig.status,
        'created_at': sig.created_at.isoformat(),
        'conclusion': (sig.explanation or {}).get('conclusion', ''),
    }


def build_overview() -> dict:
    """Dashboard payload: prices (from memory, DB fallback) + latest signal per coin."""
    coins = get_coins()
    cache = get_price_cache()
    items = []
    for coin in coins:
        cached = cache.get(coin.symbol, {})
        price = cached.get('price')
        updated_at = cached.get('updated_at')
        if price is None:
            ticker = getattr(coin, 'ticker', None)
            if ticker is not None:
                price = float(ticker.price)
                updated_at = ticker.updated_at
        items.append({
            'base_asset': coin.base_asset,
            'name': coin.name,
            'symbol': coin.symbol,
            'price': price,
            'change_24h': cached.get('change', 0.0),
            'updated_at': updated_at.isoformat() if updated_at else None,
            'signal': _last_signal_payload(coin),
        })
    last_analysis = Signal.objects.first()
    return {
        'now': timezone.now().isoformat(),
        'connected': is_connected(),
        'last_analysis_at': last_analysis.created_at.isoformat() if last_analysis else None,
        'coins': items,
    }


@api_view(['POST'])
def reconnect(request):
    """Try to ping Binance and reconnect. Returns {ok: bool, connected: bool}."""
    ok = try_reconnect()
    return Response({'ok': ok, 'connected': is_connected()})


@api_view(['GET'])
def overview(request):
    return Response(build_overview())


@api_view(['GET'])
def coin_detail(request, base_asset):
    coin = get_coin_by_base_asset(base_asset)
    if coin is None:
        return Response({'error': 'coin not found'}, status=404)

    signals = Signal.objects.filter(coin=coin)[:30]
    history = [{
        'id': s.id,
        'signal_label': SIGNAL_LABELS.get(s.signal_type, s.signal_type),
        'signal_type': s.signal_type,
        'confidence': round(s.confidence, 1),
        'status': s.status,
        'result_pnl': s.result_pnl,
        'created_at': s.created_at.isoformat(),
        'is_correct': s.is_correct,
    } for s in signals]

    latest = Signal.objects.filter(coin=coin).first()
    cached = get_price_cache().get(coin.symbol, {})

    # regime: use latest signal's snapshot; if it predates the regime feature,
    # compute a fresh one from stored 5m candles so the page always has data
    regime_data = (latest.explanation or {}).get('regime_data') if latest else None
    if not regime_data:
        try:
            from apps.analysis.engine.regime import detect_regime
            df5 = get_candles_df(coin, '5m', limit=400)
            if not df5.empty and len(df5) >= 100:
                regime_data = detect_regime(df5).to_dict()
        except Exception:
            regime_data = None

    # price: memory cache first, fall back to the last DB-saved price
    price = cached.get('price')
    updated_at = cached.get('updated_at')
    if price is None:
        ticker = getattr(coin, 'ticker', None)
        if ticker is not None:
            price = float(ticker.price)
            updated_at = ticker.updated_at

    # strategy ranking from historical performance
    strat_ranking = []
    for sp in StrategyPerformance.objects.filter(coin=coin).order_by('-accuracy_percentage')[:5]:
        strat_ranking.append({
            'strategy': sp.strategy_name,
            'strategy_fa': sp.strategy_fa,
            'accuracy': round(sp.accuracy_percentage, 1),
            'total': sp.total_predictions,
            'correct': sp.successful_predictions,
            'weight': round(sp.weight, 2),
        })

    signal_payload = _full_signal_payload(latest) if latest else None
    if signal_payload is not None and regime_data:
        signal_payload['regime'] = regime_data

    return Response({
        'base_asset': coin.base_asset,
        'name': coin.name,
        'symbol': coin.symbol,
        'price': price,
        'updated_at': updated_at.isoformat() if updated_at else None,
        'signal': signal_payload,
        'history': history,
        'strategy_ranking': strat_ranking,
        'performance': accuracy_stats(),
    })


def _full_signal_payload(sig):
    explanation = sig.explanation or {}
    regime_data = explanation.get('regime_data') or None
    # use live regime cache if available (fresher than stored snapshot)
    live_regime = get_regime(sig.coin.symbol) if hasattr(sig, 'coin') else None
    if live_regime and regime_data:
        regime_data['regime'] = live_regime
    elif live_regime and not regime_data:
        regime_data = {'regime': live_regime}
    return {
        'id': sig.id,
        'signal_type': sig.signal_type,
        'signal_label': SIGNAL_LABELS.get(sig.signal_type, sig.signal_type),
        'confidence': round(sig.confidence, 1),
        'status': sig.status,
        'result_pnl': sig.result_pnl,
        'confidence_breakdown': sig.confidence_breakdown,
        'ai_adjustment': sig.ai_adjustment,
        'risk_level': sig.risk_level,
        'direction': sig.direction,
        'trend': sig.trend or None,
        'entry': sig.entry,
        'stop_loss': sig.stop_loss,
        'take_profit': sig.take_profit,
        'risk_reward': sig.risk_reward,
        'holding_time_minutes': sig.holding_time_minutes,
        'explanation': explanation,
        'strategies': sig.strategies,
        'created_at': sig.created_at.isoformat(),
        'regime': regime_data,
        'best_strategy': explanation.get('best_strategy') or None,
        'conclusion': explanation.get('conclusion') or None,
    }


@api_view(['GET'])
def candles(request, base_asset, timeframe):
    if timeframe not in TIMEFRAME_MINUTES:
        return Response({'error': 'bad timeframe'}, status=400)
    coin = get_coin_by_base_asset(base_asset)
    if coin is None:
        return Response({'error': 'coin not found'}, status=404)
    df = get_candles_df(coin, timeframe, limit=400)
    data = [{
        'time': int(ts.timestamp()),
        'open': row['open'], 'high': row['high'],
        'low': row['low'], 'close': row['close'],
        'volume': row['volume'],
    } for ts, row in df.iterrows()]
    # overlay data: EMA lines + structure levels of the latest signal
    from apps.analysis.engine.indicators import ema
    ema_data = {}
    if not df.empty:
        for period in (20, 50):
            series = ema(df['close'], period)
            ema_data[f'ema{period}'] = [
                {'time': int(ts.timestamp()), 'value': round(float(v), 8)}
                for ts, v in series.dropna().items()
            ]
    levels = {}
    sig = Signal.objects.filter(coin=coin, direction__in=['LONG', 'SHORT']).first()
    if sig:
        levels = {
            'entry': sig.entry,
            'stop_loss': sig.stop_loss,
            'take_profit': sig.take_profit,
        }
    return Response({'timeframe': timeframe, 'candles': data, 'emas': ema_data,
                     'levels': levels})


@api_view(['GET'])
def performance(request):
    return Response(accuracy_stats())


@api_view(['GET'])
def notifications(request):
    qs = Notification.objects.all()[:30]
    return Response([{
        'id': n.id, 'title': n.title, 'message': n.message,
        'level': n.level, 'sound': n.sound,
        'created_at': n.created_at.isoformat(),
    } for n in qs])
