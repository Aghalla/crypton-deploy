// Coin detail page: chart with timeframes + live detail refresh.
const BASE = document.body.dataset.coin;
const TFS = ['1h', '30m', '15m', '5m'];
let chart, candleSeries, emaSeries = {}, currentTf = '5m';

async function loadChart(tf) {
  currentTf = tf;
  const res = await fetch(`/api/coin/${BASE}/candles/${tf}/`);
  const data = await res.json();
  candleSeries.setData(data.candles.map(c => ({
    time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
  })));
  Object.values(emaSeries).forEach(s => s.setData([]));
  for (const [key, points] of Object.entries(data.emas || {})) {
    if (!emaSeries[key]) {
      const mkLine = typeof chart.addLineSeries === 'function'
        ? (opts) => chart.addLineSeries(opts)
        : (opts) => chart.addLineChart(opts);
      emaSeries[key] = mkLine({
        color: key === 'ema20' ? '#c084fc' : '#38bdf8', lineWidth: 1,
        priceLineVisible: false, lastValueVisible: false,
      });
    }
    emaSeries[key].setData(points.map(p => ({ time: p.time, value: p.value })));
  }
  // price lines: entry / SL / TP
  const levels = data.levels || {};
  const colors = { entry: '#8b5cf6', stop_loss: '#f43f5e', take_profit: '#10b981' };
  const titles = { entry: 'ورود', stop_loss: 'حد ضرر', take_profit: 'حد سود' };
  for (const [k, v] of Object.entries(levels)) {
    if (v) candleSeries.createPriceLine({
      price: v, color: colors[k], lineWidth: 1, lineStyle: 2,
      axisLabelVisible: true, title: titles[k],
    });
  }
  chart.timeScale().fitContent();
}

function initChart() {
  const chartEl = document.getElementById('chart');
  if (!chartEl || !window.LightweightCharts) return;
  chart = LightweightCharts.createChart(chartEl, {
    layout: {
      background: { color: 'transparent' },
      textColor: '#a78bfa',
    },
    grid: {
      vertLines: { color: 'rgba(139,92,246,0.08)' },
      horzLines: { color: 'rgba(139,92,246,0.08)' },
    },
    timeScale: { timeVisible: true, secondsVisible: false },
    localization: { locale: 'fa-IR' },
    autoSize: true,
  });
  // Lightweight Charts v4 API (addCandlestickSeries); v5 renamed to addCandlestickChart
  if (typeof chart.addCandlestickSeries === 'function') {
    candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#f43f5e',
      wickUpColor: '#10b981', wickDownColor: '#f43f5e',
      borderVisible: false,
    });
  } else {
    candleSeries = chart.addCandlestickChart({
      upColor: '#10b981', downColor: '#f43f5e',
      wickUpColor: '#10b981', wickDownColor: '#f43f5e',
      borderVisible: false,
    });
  }
  document.querySelectorAll('.tf-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadChart(btn.dataset.tf);
    });
  });
  loadChart(currentTf);
  setInterval(() => loadChart(currentTf), 60000);
}

// ---------------------------------------------------------------- detail
function statusFa(s) {
  return { open: 'باز', tp: '✔ درست (هدف)', sl: '✘ غلط (ضرر)', expired: 'منقضی' }[s] || s;
}
function statusClass(s) {
  return s === 'tp' ? 'up' : s === 'sl' ? 'down' : '';
}

async function loadDetail() {
  const res = await fetch(`/api/coin/${BASE}/`);
  const d = await res.json();
  document.getElementById('coin-price').textContent = fmtPrice(d.price);
  document.getElementById('coin-updated').textContent = faTime(d.updated_at);

  const sig = d.signal;
  const sigEl = document.getElementById('current-signal');
  if (sig) {
    if (sig.signal_type === 'WAIT') {
      // WAIT signals always show as صبر — no status suffix
      sigEl.textContent = 'صبر';
      sigEl.className = 'signal-badge sig-wait';
    } else if (sig.status && sig.status !== 'open') {
      const reasons = { sl: '✘ بسته: حد ضرر', tp: '✔ بسته: هدف', expired: 'بسته: منقضی' };
      sigEl.textContent = `${sig.signal_label} — ${reasons[sig.status] || 'بسته'}`;
      sigEl.className = 'signal-badge sig-wait';
    } else {
      sigEl.textContent = `${sig.signal_label} — اعتماد ${Math.round(sig.confidence)}٪`;
      sigEl.className = 'signal-badge ' + signalClass(sig.signal_type);
    }
  }
  if (sig) {
    // AI explanation: show for the latest signal regardless of open/closed status
    document.getElementById('ai-narrative').textContent =
      (sig.explanation && sig.explanation.narrative) || '—';
    fillList('pos-list', (sig.explanation || {}).positives || []);
    fillList('neg-list', (sig.explanation || {}).negatives || []);
    fillList('risk-list', (sig.explanation || {}).risks || []);
    // trade setup: only meaningful for open actionable signals
    const isOpenActionable = (!sig.status || sig.status === 'open') && sig.signal_type !== 'WAIT';
    document.getElementById('setup-box').innerHTML = isOpenActionable ? `
      <div class="meta-row"><span>ورود</span><b>${fmtPrice(sig.entry)}</b></div>
      <div class="meta-row"><span>حد ضرر</span><b class="down">${fmtPrice(sig.stop_loss)}</b></div>
      <div class="meta-row"><span>حد سود</span><b class="up">${fmtPrice(sig.take_profit)}</b></div>
      <div class="meta-row"><span>ریسک/بازده</span><b>${sig.risk_reward}</b></div>
      <div class="meta-row"><span>مدت نگهداری مورد انتظار</span><b>${sig.holding_time_minutes} دقیقه</b></div>`
      : '<div class="meta-row"><span>سیگنال معاملاتی فعالی وجود ندارد</span></div>';
    // strategies snapshot of the latest signal
    const stratBox = document.getElementById('strategies-box');
    stratBox.innerHTML = (sig.strategies || []).map(s => `
      <div class="meta-row">
        <span>${s.name_fa}</span>
        <b>${({ BUY: 'خرید', SELL: 'فروش', WAIT: 'صبر' })[s.signal]} — قدرت ${Math.round(s.strength)}٪</b>
      </div>`).join('') || '<div class="meta-row">—</div>';
  }

  // performance
  const p = d.performance || {};
  document.getElementById('perf-total').textContent = p.total ?? 0;
  document.getElementById('perf-correct').textContent = p.correct ?? 0;
  document.getElementById('perf-wrong').textContent = p.wrong ?? 0;
  document.getElementById('perf-accuracy').textContent = (p.accuracy ?? 0) + '٪';

  // regime
  if (sig && sig.regime && sig.regime.regime) {
    const r = sig.regime;
    const regimeLabels = { trending: 'رونددار', range: 'محدوده‌ای', volatile: 'پرنوسان', quiet: 'کم‌نوسان' };
    const dirLabels = { bullish: '🟢 صعودی', bearish: '🔴 نزولی', neutral: '🟡 خنثی' };
    const volLabels = { high: 'بالا', normal: 'عادی', low: 'پایین' };
    document.getElementById('regime-box').innerHTML = `
      <div class="meta-row"><span>وضعیت بازار</span><b>${regimeLabels[r.regime] || r.regime}</b></div>
      <div class="meta-row"><span>جهت روند</span><b>${dirLabels[r.direction] || r.direction || '—'}</b></div>
      <div class="meta-row"><span>نوسان</span><b>${volLabels[r.volatility] || r.volatility || '—'}${r.vol_pct != null ? ' (' + r.vol_pct + '٪)' : ''}</b></div>
      <div class="meta-row"><span>قدرت روند</span><b>${r.trend_strength != null ? r.trend_strength : '—'}/۱۰۰</b></div>
      <div class="meta-row"><span>بهترین استراتژی</span><b>${sig.best_strategy || '—'}</b></div>`;
  } else {
    document.getElementById('regime-box').innerHTML =
      '<div class="meta-row"><span>هنوز تحلیل وضعیت بازار ثبت نشده — پس از اولین چرخه تحلیل نمایش داده می‌شود</span></div>';
  }

  // strategy ranking
  const stratRank = d.strategy_ranking || [];
  if (stratRank.length > 0) {
    document.getElementById('strategy-ranking-box').innerHTML = stratRank.map((s, i) => `
      <div class="meta-row">
        <span>${i + 1}. ${s.strategy_fa} <span style="color:var(--muted);font-size:.8rem">(${s.total} پیش‌بینی)</span></span>
        <b class="${s.accuracy >= 70 ? 'up' : s.accuracy >= 50 ? '' : 'down'}">${s.accuracy}٪</b>
      </div>`).join('');
  }

  // history
  const tbody = document.getElementById('history-body');
  tbody.innerHTML = (d.history || []).map(h => `
    <tr>
      <td>${faTime(h.created_at)}</td>
      <td><span class="signal-badge ${signalClass(h.signal_type)}">${h.signal_label}</span></td>
      <td>${Math.round(h.confidence)}٪</td>
      <td class="${statusClass(h.status)}">${statusFa(h.status)}</td>
      <td class="${(h.result_pnl ?? 0) >= 0 ? 'up' : 'down'}">${h.result_pnl == null ? '—' : h.result_pnl.toFixed(2) + '٪'}</td>
    </tr>`).join('');
}

function fillList(id, items) {
  const ul = document.getElementById(id);
  ul.innerHTML = items.map(t => `<li>${t}</li>`).join('') || '<li>موردی ثبت نشده</li>';
}

document.addEventListener('DOMContentLoaded', () => {
  try { initChart(); } catch (e) { console.error('chart init failed', e); }
  loadDetail();
  setInterval(loadDetail, 20000);
});
