"""
Signal engine: runs the full analysis pipeline for one coin and produces
(optionally) a new Signal, with duplicate prevention and expiry management.

Integrates: regime detection, strategy weights, signal quality filter,
AI explanation layer, strategy performance tracking, and full audit trail.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
from django.utils import timezone

from apps.analysis.engine.indicators import add_all_indicators
from apps.analysis.engine.multitf import analyze_multi_timeframe
from apps.analysis.engine.regime import detect_regime
from apps.market_data.models import Coin
from apps.market_data.services.data import get_candles_df
from apps.signals.confidence import (ConfidenceResult, compute_confidence,
                                     map_score_to_signal_type, risk_level_from_score)
from apps.signals.explanation import generate_explanation
from apps.signals.models import SIGNAL_LABELS, Signal, StrategyPerformance
from apps.signals.trade_setup import build_trade_setup
from apps.strategies.registry import run_all_strategies
from apps.strategies.registry import run_all_strategies

logger = logging.getLogger('crypton.signals')

# a new signal requires at least this much confidence change or price move
MIN_CONFIDENCE_DELTA = 10.0
MIN_PRICE_MOVE_RATIO = 0.004
MIN_SIGNAL_GAP_MINUTES = 30
# after an SL/TP close, block a same-direction repeat for this long
SIGNAL_COOLDOWN_MINUTES = 60


def build_feature_vector(mtf, strategy_results, confidence: ConfidenceResult,
                         setup, atr_pct: float) -> dict:
    """Flat numeric feature dict used for ML training/prediction."""
    feats = {
        'alignment': mtf.alignment,
        'h1_trend_up': 1.0 if mtf.snapshot('1h').trend == 'up' else 0.0,
        'h1_trend_down': 1.0 if mtf.snapshot('1h').trend == 'down' else 0.0,
        'h1_strength': mtf.snapshot('1h').trend_strength,
        'h1_rsi': mtf.snapshot('1h').rsi,
        'm30_strength': mtf.snapshot('30m').trend_strength,
        'm30_rsi': mtf.snapshot('30m').rsi,
        'm15_rsi': mtf.snapshot('15m').rsi,
        'm5_rsi': mtf.snapshot('5m').rsi,
        'm5_macd_hist': mtf.snapshot('5m').macd_hist,
        'm5_macd_hist_15m': mtf.snapshot('15m').macd_hist,
        'm5_vol_ratio': mtf.snapshot('5m').vol_ratio,
        'atr_pct': atr_pct,
        'confidence': confidence.score,
        'direction_long': 1.0 if confidence.direction == 'LONG' else 0.0,
        'risk_reward': setup.risk_reward if setup.risk_reward else 0.0,
    }
    # strategy votes one-hot style
    for r in strategy_results:
        key = f'strat_{r.name}'
        if r.signal == 'BUY':
            feats[key] = r.strength / 100.0
        elif r.signal == 'SELL':
            feats[key] = -r.strength / 100.0
        else:
            feats[key] = 0.0
    return feats


def _direction_hint(strategy_results):
    buys = [r for r in strategy_results if r.signal == 'BUY']
    sells = [r for r in strategy_results if r.signal == 'SELL']
    buy_power = sum(r.strength for r in buys)
    sell_power = sum(r.strength for r in sells)
    if not buys and not sells:
        return 'FLAT'
    if buy_power > sell_power * 1.2:
        return 'LONG'
    if sell_power > buy_power * 1.2:
        return 'SHORT'
    return 'FLAT'


def _should_create_signal(coin: Coin, signal_type: str, confidence: float,
                          price: float) -> bool:
    """Duplicate prevention: no repeated signals unless market changed meaningfully."""
    last = Signal.objects.filter(coin=coin).first()
    now = timezone.now()
    if last is None:
        return True
    if (now - last.created_at).total_seconds() < MIN_SIGNAL_GAP_MINUTES * 60:
        return False
    # a finished actionable signal needs a cooldown before the same side
    # may repeat — the market just proved that trade wrong/right
    if last.is_actionable and last.status != Signal.STATUS_OPEN:
        same_finished_side = (signal_type.startswith('BUY') and last.signal_type.startswith('BUY')) or \
                             (signal_type.startswith('SELL') and last.signal_type.startswith('SELL'))
        if same_finished_side and last.closed_at and \
                (now - last.closed_at).total_seconds() < SIGNAL_COOLDOWN_MINUTES * 60:
            return False
        return True
    price_move = abs(price - last.price) / last.price if last.price else 1.0
    same_side = (signal_type.startswith('BUY') and last.signal_type.startswith('BUY')) or \
                (signal_type.startswith('SELL') and last.signal_type.startswith('SELL'))
    if same_side and abs(confidence - last.confidence) < MIN_CONFIDENCE_DELTA \
            and price_move < MIN_PRICE_MOVE_RATIO:
        return False
    if signal_type == 'WAIT' and last.signal_type == 'WAIT':
        return False
    return True


def expire_stale_signals():
    """Close open signals whose expires_at passed without hitting TP/SL."""
    now = timezone.now()
    stale = Signal.objects.filter(status=Signal.STATUS_OPEN,
                                  expires_at__lt=now)
    for sig in stale:
        sig.status = Signal.STATUS_EXPIRED
        sig.closed_at = now
        sig.save(update_fields=['status', 'closed_at'])
        _finalize_signal(sig)
    return stale.count()


def _finalize_signal(sig: Signal):
    """Hook called when a signal reaches a final state: feeds the learning system."""
    try:
        from apps.learning.services import record_signal_outcome
        record_signal_outcome(sig)
    except Exception:
        logger.exception('failed to feed learning system for signal %s', sig.id)
    try:
        from apps.notifications.services import notify_signal_closed
        notify_signal_closed(sig)
    except Exception:
        pass


def close_signal(sig: Signal, status: str, pnl: float):
    sig.status = status
    sig.result_pnl = pnl
    sig.closed_at = timezone.now()
    sig.save(update_fields=['status', 'result_pnl', 'closed_at'])
    # track strategy performance on close
    _update_strategy_performance_on_close(sig, status)
    _finalize_signal(sig)
    # immediately produce a fresh WAIT signal so the user knows the situation changed
    try:
        analyze_coin(sig.coin, force_wait=True)
    except Exception:
        logger.exception('failed to generate follow-up signal for %s', sig.coin.symbol)


def check_open_signals(coin: Coin):
    """Update open signals of a coin against the latest price and candle high/low."""
    from apps.market_data.services.data import get_price_cache
    cached = get_price_cache().get(coin.symbol, {})
    price = cached.get('price')
    if price is None:
        return
    price = float(price)
    # get latest 5m candle high/low for more accurate TP/SL detection
    candle_high, candle_low = price, price
    from apps.market_data.services.data import get_candles_df
    try:
        df5 = get_candles_df(coin, '5m', limit=2)
        if len(df5) >= 1:
            last_candle = df5.iloc[-1]
            candle_high = float(last_candle['high'])
            candle_low = float(last_candle['low'])
    except Exception:
        pass

    for sig in Signal.objects.filter(coin=coin, status=Signal.STATUS_OPEN):
        if sig.signal_type == 'WAIT' or sig.direction == 'FLAT':
            if sig.expires_at and timezone.now() > sig.expires_at:
                close_signal(sig, Signal.STATUS_EXPIRED, 0.0)
            continue
        long_trade = sig.direction == 'LONG'
        # check both tick price and candle high/low
        tp_hit = (price >= sig.take_profit or candle_high >= sig.take_profit) if long_trade \
            else (price <= sig.take_profit or candle_low <= sig.take_profit)
        sl_hit = (price <= sig.stop_loss or candle_low <= sig.stop_loss) if long_trade \
            else (price >= sig.stop_loss or candle_high >= sig.stop_loss)
        # if both TP and SL could have been hit in same candle, prefer SL (conservative)
        if tp_hit and sl_hit:
            pnl = (sig.stop_loss - sig.entry) / sig.entry * (1 if long_trade else -1) * 100
            close_signal(sig, Signal.STATUS_SL, round(pnl, 3))
        elif tp_hit:
            pnl = (sig.take_profit - sig.entry) / sig.entry * (1 if long_trade else -1) * 100
            close_signal(sig, Signal.STATUS_TP, round(pnl, 3))
        elif sl_hit:
            pnl = (sig.stop_loss - sig.entry) / sig.entry * (1 if long_trade else -1) * 100
            close_signal(sig, Signal.STATUS_SL, round(pnl, 3))
        elif sig.expires_at and timezone.now() > sig.expires_at:
            pnl = (price - sig.entry) / sig.entry * (1 if long_trade else -1) * 100
            close_signal(sig, Signal.STATUS_EXPIRED, round(pnl, 3))


def analyze_coin(coin: Coin, force_wait: bool = False) -> Signal | None:
    """
    Run the full analysis pipeline for one coin.

    Pipeline:
    candles -> indicators -> structure -> regime -> MTF -> strategies (weighted)
    -> confidence -> ML adjustment -> signal quality filter -> explanation
    -> strategy performance tracking -> create Signal with full audit trail.

    force_wait: when True (e.g. after SL/TP close), always produce a WAIT signal
                and skip dedup so the user sees the situation has changed.
    """
    dfs = {}
    for tf in ('1h', '30m', '15m', '5m'):
        dfs[tf] = get_candles_df(coin, tf, limit=400)
        if dfs[tf].empty:
            logger.warning('no candles for %s %s — skipping analysis', coin.symbol, tf)
            return None

    # --- 1. Market Regime Detection ---
    regime = detect_regime(dfs['5m'], dfs.get('1h'))
    # --- 2. Multi-timeframe analysis ---
    mtf = analyze_multi_timeframe(dfs)
    # Always publish the freshest trend/regime so the dashboard is live
    from apps.market_data.services.data import set_mtf_bias, set_regime
    set_mtf_bias(coin.symbol, mtf.bias())
    set_regime(coin.symbol, regime.regime)
    # keep regime direction consistent with the multi-timeframe view
    regime.direction = mtf.bias()

    # --- 3. Run strategies with regime-adjusted weights ---
    strategy_results = run_all_strategies(mtf, df_5m=dfs['5m'],
                                           regime_weights=regime.strategy_weights)

    # --- 4. Direction from strategy votes ---
    direction = _direction_hint(strategy_results)

    # --- 5. Confidence score ---
    confidence = compute_confidence(mtf, strategy_results, direction)

    # --- 6. Trade setup ---
    m5 = mtf.snapshot('5m')
    atr_pct = m5.atr / m5.price if m5.price else 0.0
    setup = build_trade_setup(direction if direction in ('LONG', 'SHORT') else 'FLAT',
                              m5.price, m5.atr, m5.structure)

    # --- 7. ML adjustment + success probability ---
    features = build_feature_vector(mtf, strategy_results, confidence, setup, atr_pct)
    adjustment = 0.0
    success_probability = 50.0
    try:
        from apps.learning.services import predict_adjustment, predict_success_probability
        adjustment = predict_adjustment(features, direction)
        success_probability = predict_success_probability(features, direction)
    except Exception:
        logger.exception('ML prediction failed for %s', coin.symbol)
    adjusted = max(0.0, min(100.0, confidence.score + adjustment))

    # --- 8. Signal type ---
    if force_wait:
        signal_type = 'WAIT'
    else:
        signal_type = map_score_to_signal_type(adjusted, direction) \
            if direction in ('LONG', 'SHORT') else 'WAIT'
    risk_level = risk_level_from_score(adjusted, atr_pct)

    # --- 9. Signal Quality Filter ---
    if not force_wait and signal_type != 'WAIT':
        if adjusted < 55:
            logger.info('%s: signal %s blocked (confidence %.1f < 55)',
                        coin.symbol, signal_type, adjusted)
            signal_type = 'WAIT'
        elif setup.risk_reward < 1.5:
            logger.info('%s: signal %s blocked (R/R %.2f < 1.5)',
                        coin.symbol, signal_type, setup.risk_reward)
            signal_type = 'WAIT'
        # timeframe alignment: if major timeframes disagree, downgrade to WAIT
        if signal_type != 'WAIT' and mtf.alignment * (1 if direction == 'LONG' else -1) < -30:
            logger.info('%s: signal %s blocked (MTF misaligned %.1f)',
                        coin.symbol, signal_type, mtf.alignment)
            signal_type = 'WAIT'

    # rebuild setup if direction became actionable, so entry levels reflect price
    if signal_type != 'WAIT' and direction in ('LONG', 'SHORT'):
        setup = build_trade_setup(direction, m5.price, m5.atr, m5.structure)

    # --- 10. Dedup check (force_wait bypasses) ---
    if not force_wait and not _should_create_signal(coin, signal_type, adjusted, m5.price):
        return None

    # --- 11. AI Explanation Layer ---
    explanation = generate_explanation(mtf, strategy_results, confidence, regime,
                                       signal_type, direction, atr_pct)
    # add ML success probability
    if signal_type != 'WAIT' and direction in ('LONG', 'SHORT'):
        explanation.positives.append(
            f'مدل AI احتمال موفقیت را {success_probability:.0f}٪ پیش‌بینی کرد')
        if success_probability < 55:
            explanation.risks.append(
                f'مدل AI احتمال موفقیت پایین ({success_probability:.0f}٪) پیش‌بینی کرده')

    # --- 12. Force-wait: detect reason ---
    if force_wait:
        prev = Signal.objects.filter(coin=coin).exclude(id__isnull=True).order_by('-created_at').first()
        reason = 'سیگنال قبلی بسته شد'
        if prev and prev.status == 'sl':
            reason = 'سیگنال قبلی به حد ضرر رسید و بازار را رد کرد'
        elif prev and prev.status == 'tp':
            reason = 'سیگنال قبلی به هدف رسید'
        elif prev and prev.status == 'expired':
            reason = 'سیگنال قبلی منقضی شد'
        trend_change = ''
        if prev and prev.direction in ('LONG', 'SHORT'):
            old_side = 'bullish' if prev.direction == 'LONG' else 'bearish'
            new_side = mtf.bias()
            if old_side != new_side and new_side != 'neutral':
                trend_change = f' و روند از {old_side} به {new_side} تغییر کرد'
        explanation.reason_fa = f'{reason}{trend_change}. {explanation.reason_fa}'
        explanation.conclusion_fa = 'صبر کنید تا شرایط ورود مناسب مجدد فراهم شود.'

    # --- 13. Strategy snapshot with weights ---
    strat_snapshot = [r.to_dict() for r in strategy_results]
    for s in strat_snapshot:
        s['regime_weight'] = regime.strategy_weights.get(s['name'], 1.0)

    # --- 14. Build full explanation dict (audit trail) ---
    dir_fa = 'خرید' if direction == 'LONG' else 'فروش' if direction == 'SHORT' else 'صبر'
    if signal_type != 'WAIT':
        narrative = (
            f'{mtf.summary_fa} {confidence.narrative_fa} '
            f'مدل یادگیری ماشین امتیاز را {adjustment:+.1f} تعدیل کرد. '
            f'نتیجه نهایی: {SIGNAL_LABELS[signal_type]}.'
        )
    elif force_wait:
        narrative = explanation.reason_fa
    else:
        narrative = (
            f'{mtf.summary_fa} {confidence.narrative_fa} '
            f'شرایط برای {dir_fa} فراهم نیست؛ سیگنال صبر.'
        )

    full_explanation = {
        'narrative': narrative,
        'reason': explanation.reason_fa,
        'positives': explanation.positives,
        'negatives': explanation.negatives,
        'risks': explanation.risks,
        'confidence_reason': explanation.confidence_reason_fa,
        'best_strategy': explanation.best_strategy_fa,
        'regime': explanation.regime_fa,
        'conclusion': explanation.conclusion_fa,
        'trade_setup': setup.explanation_fa,
        'mtf_summary': mtf.summary_fa,
        # full audit: indicators snapshot
        'indicators_5m': {
            'rsi': round(m5.rsi, 1),
            'macd_hist': round(m5.macd_hist, 6),
            'ema_bias': m5.ema_bias,
            'vol_ratio': round(m5.vol_ratio, 2),
            'atr': round(m5.atr, 8),
            'trend': m5.trend,
        },
        'indicators_1h': {
            'trend': mtf.snapshot('1h').trend,
            'strength': round(mtf.snapshot('1h').trend_strength, 1),
            'ema_bias': mtf.snapshot('1h').ema_bias,
        },
        'regime_data': regime.to_dict(),
        'success_probability': success_probability,
    }

    # --- 15. Create Signal ---
    signal = Signal.objects.create(
        coin=coin,
        signal_type=signal_type,
        confidence=adjusted,
        direction=direction if signal_type != 'WAIT' else 'FLAT',
        price=m5.price,
        entry=setup.entry if signal_type != 'WAIT' else m5.price,
        stop_loss=setup.stop_loss if signal_type != 'WAIT' else 0.0,
        take_profit=setup.take_profit if signal_type != 'WAIT' else 0.0,
        risk_reward=setup.risk_reward,
        holding_time_minutes=setup.holding_time_minutes,
        risk_level=risk_level,
        trend=mtf.bias(),
        explanation=full_explanation,
        strategies=strat_snapshot,
        confidence_breakdown=confidence.breakdown,
        features=features,
        ai_adjustment=adjustment,
        expires_at=timezone.now() + timedelta(
            minutes=max(setup.holding_time_minutes, 60) * 2 if signal_type != 'WAIT' else 120),
    )

    # --- 16. Strategy Performance tracking ---
    _update_strategy_performance(coin, strategy_results, signal_type, direction)

    # --- 17. Side effects ---
    if signal.is_actionable:
        try:
            from apps.notifications.services import notify_new_signal
            notify_new_signal(signal)
        except Exception:
            logger.exception('notification failed')
        try:
            from apps.paper_trading.services import open_paper_trade
            open_paper_trade(signal)
        except Exception:
            logger.exception('paper trade creation failed')

    logger.info('new signal for %s: %s (confidence %.1f, ml %+.1f, regime=%s)',
                coin.symbol, signal_type, adjusted, adjustment, regime.regime)
    try:
        from apps.core.worker import broadcast_signal
        broadcast_signal(signal)
    except Exception:
        pass
    return signal


def _update_strategy_performance(coin, strategy_results, signal_type, direction):
    """
    Update StrategyPerformance records after each signal.
    When a signal is closed as TP/SL, the strategies that agreed get +1 success
    or +1 failure. This runs at signal CREATION time to track agreement rate.
    """
    if signal_type == 'WAIT':
        return
    for result in strategy_results:
        if result.signal == 'WAIT':
            continue
        agrees = (result.signal == 'BUY' and direction == 'LONG') or \
                 (result.signal == 'SELL' and direction == 'SHORT')
        sp, _ = StrategyPerformance.objects.get_or_create(
            coin=coin, strategy_name=result.name,
            defaults={'strategy_fa': result.name_fa})
        sp.total_predictions += 1
        if agrees:
            sp.successful_predictions += 1
        else:
            sp.failed_predictions += 1
        sp.accuracy_percentage = (
            sp.successful_predictions / sp.total_predictions * 100
            if sp.total_predictions > 0 else 0.0)
        sp.save(update_fields=['total_predictions', 'successful_predictions',
                               'failed_predictions', 'accuracy_percentage'])


def _update_strategy_performance_on_close(sig: Signal, status: str):
    """
    When a signal is closed (TP/SL/expired), update the StrategyPerformance
    for each strategy that agreed with the signal direction.
    TP = correct prediction, SL/expired = incorrect.
    """
    if not sig.strategies or sig.direction == 'FLAT':
        return
    is_correct = (status == Signal.STATUS_TP)
    for strat in sig.strategies:
        strat_name = strat.get('name', '')
        agrees = (strat.get('signal') == 'BUY' and sig.direction == 'LONG') or \
                 (strat.get('signal') == 'SELL' and sig.direction == 'SHORT')
        if not agrees:
            continue
        sp, _ = StrategyPerformance.objects.get_or_create(
            coin=sig.coin, strategy_name=strat_name,
            defaults={'strategy_fa': strat.get('name_fa', strat_name)})
        sp.total_predictions += 1
        if is_correct:
            sp.successful_predictions += 1
        else:
            sp.failed_predictions += 1
        sp.accuracy_percentage = (
            sp.successful_predictions / sp.total_predictions * 100
            if sp.total_predictions > 0 else 0.0)
        sp.save(update_fields=['total_predictions', 'successful_predictions',
                               'failed_predictions', 'accuracy_percentage'])
