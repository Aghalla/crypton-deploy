// Dashboard realtime logic: WebSocket + fallback polling, notifications, sound.
function fmtPrice(p) {
  if (p == null) return '—';
  return Number(p).toLocaleString('en-US', { maximumFractionDigits: 8 });
}
function faTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString('fa-IR') + ' — ' + d.toLocaleDateString('fa-IR');
}
function signalClass(t) {
  if (!t) return 'sig-wait';
  if (t.startsWith('BUY')) return 'sig-buy';
  if (t.startsWith('SELL')) return 'sig-sell';
  return 'sig-wait';
}
function trendFa(align) { return align > 40 ? 'صعودی' : align < -40 ? 'نزولی' : 'خنثی'; }

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = 880; gain.gain.value = 0.08;
    osc.start();
    setTimeout(() => { osc.stop(); ctx.close(); }, 350);
  } catch (e) { /* autoplay blocked until user interacts */ }
}

function toast(title, msg) {
  const panel = document.getElementById('notif-panel');
  if (!panel) return;
  const el = document.createElement('div');
  el.className = 'toast';
  el.innerHTML = `<b>${title}</b><span>${msg || ''}</span>`;
  panel.appendChild(el);
  setTimeout(() => el.remove(), 12000);
}

function connectDashboard() {
  let ws;
  let fallbackTimer = null;
  const startFallback = () => {
    if (fallbackTimer) return;
    fallbackTimer = setInterval(async () => {
      const res = await fetch('/api/overview/');
      applyOverview(await res.json());
    }, 15000);
  };
  try {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/dashboard/`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'overview') applyOverview(msg.payload);
      if (msg.type === 'signal') onSignalEvent(msg.payload);
    };
    ws.onclose = startFallback;
    ws.onerror = () => ws.close();
  } catch (e) { startFallback(); }
}

function onSignalEvent(p) {
  toast(`سیگنال جدید: ${p.coin}`, `${p.signal_label} با اعتماد ${Math.round(p.confidence)}٪`);
  if (p.sound) beep();
}

function applyOverview(data) {
  document.getElementById('server-now').textContent =
    new Date(data.now).toLocaleTimeString('fa-IR');
  document.getElementById('server-date').textContent =
    new Date(data.now).toLocaleDateString('fa-IR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  document.getElementById('last-analysis').textContent = faTime(data.last_analysis_at);

  (data.coins || []).forEach((c) => {
    const priceEl = document.getElementById(`price-${c.base_asset}`);
    if (priceEl) priceEl.textContent = fmtPrice(c.price);
    const upEl = document.getElementById(`updated-${c.base_asset}`);
    if (upEl) upEl.textContent = faTime(c.updated_at);
    const chEl = document.getElementById(`change-${c.base_asset}`);
    if (chEl) {
      chEl.textContent = `${c.change_24h >= 0 ? '+' : ''}${Number(c.change_24h).toFixed(2)}٪ ۲۴س`;
      chEl.className = 'coin-change ' + (c.change_24h >= 0 ? 'up' : 'down');
    }
    const sig = c.signal;
    const sigEl = document.getElementById(`signal-${c.base_asset}`);
    if (sigEl && sig) {
      if (sig.signal_type === 'WAIT') {
        // WAIT signals always show as صبر — no status suffix
        sigEl.textContent = 'صبر';
        sigEl.className = 'signal-badge sig-wait';
      } else if (sig.status && sig.status !== 'open') {
        const reasons = { sl: '✘ حد ضرر', tp: '✔ هدف', expired: 'منقضی' };
        sigEl.textContent = `${sig.signal_label} — ${reasons[sig.status] || 'بسته'}`;
        sigEl.className = 'signal-badge sig-wait';
      } else {
        sigEl.textContent = sig.signal_label || '—';
        sigEl.className = 'signal-badge ' + signalClass(sig.signal_type);
      }
    }
    const confEl = document.getElementById(`conf-${c.base_asset}`);
    const confBar = document.getElementById(`confbar-${c.base_asset}`);
    if (confEl && sig) confEl.textContent = Math.round(sig.confidence) + '٪';
    if (confBar && sig) confBar.style.width = Math.round(sig.confidence) + '%';
    const riskEl = document.getElementById(`risk-${c.base_asset}`);
    if (riskEl && sig) {
      const risks = { low: 'کم', medium: 'متوسط', high: 'زیاد' };
      riskEl.textContent = risks[sig.risk_level] || sig.risk_level;
      riskEl.className = 'risk-' + (sig.risk_level || 'medium');
    }
    const trendEl = document.getElementById(`trend-${c.base_asset}`);
    if (trendEl && sig) {
      const trendFa = { up: '🟢 صعودی', bullish: '🟢 صعودی',
                         down: '🔴 نزولی', bearish: '🔴 نزولی',
                         sideways: '🟡 خنثی', neutral: '🟡 خنثی' };
      const raw = sig.trend || '';
      trendEl.textContent = trendFa[raw] || (raw ? raw : '—');
      trendEl.className = 'trend-' + (raw || 'unknown');
    }
    const regimeEl = document.getElementById(`regime-${c.base_asset}`);
    if (regimeEl && sig) {
      const regimeLabels = { trending: '📈 رونددار', range: '📊 محدوده‌ای',
                             volatile: '⚡ پرنوسان', quiet: '😴 کم‌نوسان' };
      const raw = sig.regime || '';
      regimeEl.textContent = regimeLabels[raw] || (raw ? raw : '—');
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  fetch('/api/overview/').then(r => r.json()).then(applyOverview).catch(() => {});
  connectDashboard();
});
