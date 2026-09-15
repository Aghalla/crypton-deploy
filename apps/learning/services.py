"""
Internal AI learning system — scikit-learn based, no external AI APIs.

- The model predicts the probability that a LONG/SHORT setup hits TP before SL.
- That probability is converted into a confidence adjustment (-15..+15).
- New closed signals become live training samples; after enough of them the
  model is retrained (continuous learning).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import cross_val_score

from apps.learning.models import ModelMetadata, TrainingSample

logger = logging.getLogger('crypton.learning')

MODEL_FILENAME = 'signal_model.joblib'
ADJUSTMENT_CAP = 15.0


def _models_dir() -> Path:
    path = Path(settings.AI_MODELS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_active_model():
    meta = ModelMetadata.objects.first()
    if meta is None:
        return None, None
    model_file = _models_dir() / meta.model_file
    if not model_file.exists():
        return None, meta
    try:
        bundle = joblib.load(model_file)
        return bundle, meta
    except Exception:
        logger.exception('failed to load model')
        return None, meta


def predict_adjustment(features: dict, direction: str) -> float:
    """Return a confidence adjustment in [-15, +15] from the trained model."""
    if direction not in ('LONG', 'SHORT'):
        return 0.0
    bundle, _meta = get_active_model()
    if bundle is None:
        return 0.0
    names = bundle['feature_names']
    x = np.array([[float(features.get(n, 0.0)) for n in names]])
    proba = bundle['model'].predict_proba(x)[0][1]   # P(success)
    # centered around 0.5, signed by trade side
    edge = (proba - 0.5) * 2.0
    return round(float(np.clip(edge * ADJUSTMENT_CAP, -ADJUSTMENT_CAP, ADJUSTMENT_CAP)), 2)


def predict_success_probability(features: dict, direction: str) -> float:
    """Return the raw probability (0..100) that a trade will hit TP before SL."""
    if direction not in ('LONG', 'SHORT'):
        return 50.0
    bundle, _meta = get_active_model()
    if bundle is None:
        return 50.0
    names = bundle['feature_names']
    x = np.array([[float(features.get(n, 0.0)) for n in names]])
    try:
        proba = bundle['model'].predict_proba(x)[0][1]   # P(success)
        return round(proba * 100, 1)
    except Exception:
        return 50.0


def train_model(min_samples: int = 200) -> dict:
    """Train a new model on all labeled samples (history + live)."""
    samples = TrainingSample.objects.filter(label__isnull=False)
    data = list(samples.values_list('features', 'label'))
    if len(data) < min_samples:
        return {'trained': False, 'reason': f'only {len(data)} labeled samples (< {min_samples})'}

    names = sorted({k for feats, _ in data for k in feats})
    X = np.array([[float(feats.get(n, 0.0)) for n in names] for feats, _ in data])
    y = np.array([1 if lbl else 0 for _, lbl in data])

    clf = HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.08, max_depth=6,
        l2_regularization=1.0, random_state=42)
    try:
        cv = cross_val_score(clf, X, y, cv=5, scoring='accuracy')
        cv_accuracy = float(cv.mean())
    except Exception:
        cv_accuracy = 0.0
    clf.fit(X, y)

    version = (ModelMetadata.objects.count() or 0) + 1
    model_file = f'{MODEL_FILENAME}'
    joblib.dump({'model': clf, 'feature_names': names}, _models_dir() / model_file)
    ModelMetadata.objects.create(
        model_file=model_file, n_samples=len(data),
        cv_accuracy=cv_accuracy, feature_names=names, version=version)
    logger.info('model trained: %d samples, cv_acc=%.3f', len(data), cv_accuracy)
    return {'trained': True, 'n_samples': len(data), 'cv_accuracy': cv_accuracy}


def maybe_retrain() -> bool:
    """Retrain once AI_RETRAIN_THRESHOLD new live samples accumulated since last training."""
    from django.conf import settings as s
    meta = ModelMetadata.objects.first()
    if meta is None:
        return False
    live_since = TrainingSample.objects.filter(source='live',
                                               recorded_at__gt=meta.trained_at).count()
    if live_since >= s.AI_RETRAIN_THRESHOLD:
        result = train_model(min_samples=1)
        return bool(result.get('trained'))
    return False


def record_signal_outcome(signal):
    """Store the outcome of a closed actionable signal as a live training sample."""
    if not signal.is_actionable or signal.direction == 'FLAT':
        return
    label = signal.status == 'tp'
    TrainingSample.objects.create(
        coin=signal.coin,
        signal=signal,
        created_at=signal.created_at,
        features=signal.features or {},
        label=label,
        source='live',
    )
    logger.info('live sample recorded for %s (label=%s)', signal.coin.symbol, label)
    try:
        maybe_retrain()
    except Exception:
        logger.exception('retrain check failed')


def accuracy_stats() -> dict:
    """Overall / per-coin / per-strategy / recent accuracy of actionable signals."""
    from apps.signals.models import Signal
    actionable = Signal.objects.exclude(signal_type='WAIT').exclude(status='open')

    total = actionable.count()
    correct = actionable.filter(status='tp').count()
    wrong = actionable.filter(status='sl').count()
    expired = actionable.filter(status='expired').count()

    per_coin = []
    for row in (actionable.values('coin__base_asset')
                .annotate(n=Count('id'), c=Count('id', filter=Q(status='tp')))
                .order_by('coin__base_asset')):
        per_coin.append({
            'coin': row['coin__base_asset'],
            'total': row['n'],
            'correct': row['c'],
            'accuracy': round(row['c'] / row['n'] * 100, 1) if row['n'] else 0.0,
        })

    # per-strategy accuracy: a signal counts as supported by strategy S if S
    # voted in the signal's direction
    per_strategy = []
    for strat_key, strat_fa in [
        ('trend_following', 'روندگیری'), ('breakout', 'شکست سطح'),
        ('pullback', 'ورود در اصلاح'), ('momentum', 'مومنتوم'), ('range', 'محدوده'),
    ]:
        n = c = 0
        for sig in actionable.only('id', 'direction', 'status', 'strategies')[:2000]:
            strats = {s.get('name'): s for s in (sig.strategies or [])}
            s = strats.get(strat_key)
            if not s or s.get('signal') not in ('BUY', 'SELL'):
                continue
            agrees = (s['signal'] == 'BUY') == (sig.direction == 'LONG')
            if not agrees:
                continue
            n += 1
            if sig.status == 'tp':
                c += 1
        per_strategy.append({
            'strategy': strat_key, 'strategy_fa': strat_fa,
            'total': n, 'correct': c,
            'accuracy': round(c / n * 100, 1) if n else 0.0,
        })

    recent = actionable.order_by('-created_at')[:50]
    recent_n = recent.count()
    recent_c = sum(1 for s in recent if s.status == 'tp')

    avg_pnl = 0.0
    pnls = [s.result_pnl for s in actionable if s.result_pnl is not None]
    if pnls:
        avg_pnl = round(sum(pnls) / len(pnls), 3)

    return {
        'total': total,
        'correct': correct,
        'wrong': wrong,
        'expired': expired,
        'accuracy': round(correct / total * 100, 1) if total else 0.0,
        'recent_accuracy': round(recent_c / recent_n * 100, 1) if recent_n else 0.0,
        'avg_pnl': avg_pnl,
        'per_coin': per_coin,
        'per_strategy': per_strategy,
    }
