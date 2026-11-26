// Suhail Hunter on Cloudflare Workers (free plan): SPX morning call, first-hour update, evening result.
// The only notification channel is Telegram. No GitHub Actions, no paid service, no stored state: every
// message is rebuilt from public Yahoo data, and the live record is recomputed from 2026-11-16 each time.
// Port of range_alert/{daily_range,first_hour,promotion,explosion}.py. The numbers and research references are
// the same as in those files; see research/*/README.md in the repository.
//
// Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. Optional secret RUN_KEY enables manual runs:
//   https://<worker>/run?job=morning|firsthour|evening&key=<RUN_KEY>[&send=0]
// Schedule: one cron "*/5 * * * *". Each job fires on the 5-minute tick of its New York time; the breakout detector runs
// on every in-session tick and sends a signal once, on the tick after its entry bar completes.

// ---------- research constants (see the Python sources) ----------
const K_HIGH = 0.174, HIT_HIGH = 72, K_LOW = 0.11, HIT_LOW = 69, UP_RATE = 54, RANGE_RATE = 69;
const GAP_BUCKETS = [[-9e9, -0.5, 10], [-0.5, -0.2, 26], [-0.2, -0.05, 40], [-0.05, 0.05, 49], [0.05, 0.2, 66], [0.2, 0.5, 76], [0.5, 9e9, 89]];
const OPEN_BUCKETS = [[-9e9, -0.5, 41], [-0.5, -0.2, 49], [-0.2, 0.2, 54], [0.2, 0.5, 60], [0.5, 9e9, 61]];
const OPEN_LEVELS = [[0.1, 85, 80], [0.25, 63, 60]];
const TRADE_K = 0.5, DIR_K = 0.2, COST_PT = 1.0, MIN_TRADES = 30, MIN_DIR = 40;
const LIVE_START = '2026-11-16';
const EXT_UP = [0.289, 0.594], EXT_DN = [0.294, 0.736], COV_UP = [75, 95], COV_DN = [74, 92];
const P_BREAK_UP = 64, P_BREAK_DN = 57, P_ONE_HOLDS = 76, R1_CUTS = [0.339, 0.472], BIG_RATES = [14, 21, 29], BIG_K = 0.5;
const MODEL = {"k_explode": 0.75, "mean": [0.02117249568994317, 0.2044527212204415, 18.510666511385867, 0.3277359860781731, 1.4028110410137073, 0.9144511202362436, 0.49673725835317767, 0.9208171913091644, 0.9344621022574651, 0.5438681531749879, 2.0181774115365974], "std": [0.30624663759632215, 0.22898550696102052, 6.777053830528105, 8.325804513537658, 0.4062804931086473, 0.4073922309141946, 0.4138912916785348, 0.27259360190370996, 0.23094733304111772, 0.4980718674428483, 1.3988462712129295], "coef": [-0.10686327291057414, 0.10550454663025394, 0.18858393669272358, -0.010201855876455017, 0.20630895274047084, 0.20879550762219665, -0.21964431699464348, 0.23835296071673537, 0.20214525225343052, -0.13509693584933322, 0.06395202325136996], "intercept": -1.287491762697664, "tiers": [{"key": "high", "label": "مرتفع", "min_p": 0.423312661658646, "rate": 35}], "base_rate": 19, "trained_through": "2026-11-18"};

// ---------- NYSE calendar (nyse.com, checked 2026-11-24). Extend each year. ----------
const HOLIDAYS = new Set(['2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03',
  '2026-09-07', '2026-11-26', '2026-12-25', '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31',
  '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24']);
const EARLY_CLOSE = new Set(['2026-11-27', '2026-12-24', '2027-11-26']);
const CAL_LAST = '2027-12-31';

const NY_FMT = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, weekday: 'short' });
const RY_FMT = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Riyadh', hour: '2-digit', minute: '2-digit', hour12: false });

export function ny(date) {
  const p = Object.fromEntries(NY_FMT.formatToParts(date).map(x => [x.type, x.value]));
  const hour = p.hour === '24' ? 0 : +p.hour;
  return { iso: `${p.year}-${p.month}-${p.day}`, hour, minute: +p.minute, mins: hour * 60 + +p.minute };
}
export const riyadh = d => RY_FMT.format(d);
const addDays = (iso, k) => new Date(Date.parse(iso + 'T12:00:00Z') + k * 864e5).toISOString().slice(0, 10);
const weekday = iso => new Date(iso + 'T12:00:00Z').getUTCDay();
export const isSession = iso => weekday(iso) % 6 !== 0 && !HOLIDAYS.has(iso);
export function prevSession(iso) { let d = addDays(iso, -1); while (!isSession(d)) d = addDays(d, -1); return d; }
export function nextSession(iso) { let d = addDays(iso, 1); while (!isSession(d)) d = addDays(d, 1); return d; }
export const closeMins = iso => (EARLY_CLOSE.has(iso) ? 13 * 60 : 16 * 60);
// UTC instant of a New York wall-clock time (handles DST by probing the offset).
export function nyInstant(iso, mins) {
  const guess = Date.parse(`${iso}T00:00:00Z`) + mins * 6e4 + 5 * 36e5;
  const off = ny(new Date(guess)).mins - mins;
  return new Date(guess - ((off + 1440 + 720) % 1440 - 720) * 6e4);
}

// ---------- data (Yahoo chart API, delayed) ----------
const HOSTS = ['query1.finance.yahoo.com', 'query2.finance.yahoo.com'];
export async function chart(symbol, query, fetcher = fetch) {
  let last;
  for (const h of HOSTS) {
    try {
      const r = await fetcher(`https://${h}/v8/finance/chart/${encodeURIComponent(symbol)}?${query}`, { headers: { 'User-Agent': 'Mozilla/5.0 (suhail-hunter worker)' } });
      if (!r.ok) { last = new Error(`HTTP ${r.status}`); continue; }
      const res = (await r.json())?.chart?.result?.[0];
      if (res?.timestamp?.length) return res;
      last = new Error('empty');
    } catch (e) { last = e; }
  }
  throw new Error(`Yahoo ${symbol}: ${last?.message || last}`);
}
// Completed daily bars {iso: [o,h,l,c]} from `start`; today's bar kept only once its session has closed.
export async function daily(symbol, start, now, fetcher) {
  const p1 = Math.floor(Date.parse(start + 'T00:00:00Z') / 1000), p2 = Math.floor(now.getTime() / 1000);
  const r = await chart(symbol, `interval=1d&period1=${p1}&period2=${p2}`, fetcher);
  const q = r.indicators.quote[0], out = {}, t = ny(now);
  r.timestamp.forEach((ts, i) => {
    const v = [q.open[i], q.high[i], q.low[i], q.close[i]];
    if (v.some(x => x == null)) return;
    out[ny(new Date(ts * 1000)).iso] = v;
  });
  if (out[t.iso] && t.mins < closeMins(t.iso) + 15) delete out[t.iso];
  return out;
}
export async function bars5m(symbol, range, now, fetcher, prepost = false) {
  const r = await chart(symbol, `interval=5m&range=${range}${prepost ? '&includePrePost=true' : ''}`, fetcher);
  const q = r.indicators.quote[0];
  return r.timestamp.map((ts, i) => ({ t: new Date(ts * 1000), h: q.high[i], l: q.low[i], c: q.close[i] }))
    .filter(b => b.c != null && b.t <= now);
}

// ---------- shared math ----------
const sqrt252 = Math.sqrt(252);
export const expectedMove = (pc, vix) => pc * vix / 100 / sqrt252;
const fmt = x => Math.round(x).toLocaleString('en-US');
const pct = x => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(2) + '%';
export function wilson(k, n, z = 1.96) {
  if (!n) return [0, 1];
  const p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
  return [c - h, c + h];
}
function meanCi(x, z = 1.96) {
  if (x.length < 2) return [-Infinity, Infinity];
  const m = x.reduce((a, b) => a + b, 0) / x.length, sd = Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / (x.length - 1));
  return [m - z * sd / Math.sqrt(x.length), m + z * sd / Math.sqrt(x.length)];
}
export function gapDirection(g) {
  for (const [lo, hi, pUp] of GAP_BUCKETS) if (lo <= g && g < hi) {
    if (pUp >= 55) return ['up', 'صاعد 📈', pUp];
    if (pUp <= 45) return ['down', 'هابط 📉', 100 - pUp];
    return ['flat', 'محايد ↔️', Math.max(pUp, 100 - pUp)];
  }
}
export function openOdds(g) { for (const [lo, hi, p] of OPEN_BUCKETS) if (lo <= g && g < hi) return [p, 100 - p]; }

// ---------- explosion model (explosion.py) ----------
export function explosionFeatures(dayIso, rows, vix, anchor) {
  const p = rows.at(-1), pp = rows.at(-2), pc = p[4], v = vix[p[0]], m = expectedMove(pc, v);
  const px = rows.slice(-22).map(r => r[4]);
  let s = 0; for (let i = 1; i < px.length; i++) s += Math.log(px[i] / px[i - 1]) ** 2;
  const rv = Math.sqrt(s * 252 / 21) * 100, rng = r => (r[2] - r[3]) / m, mean = a => a.reduce((x, y) => x + y, 0) / a.length;
  const g = (anchor - pc) / m;
  const wd = (weekday(dayIso) + 6) % 7;   // Python weekday(): Monday = 0
  return [[g, Math.abs(g), v, 100 * (v / vix[pp[0]] - 1), v / rv, (p[2] - p[3]) / m, Math.abs(p[4] - p[1]) / m,
    mean(rows.slice(-5).map(rng)), mean(rows.slice(-20).map(rng)), pc > pp[4] ? 1 : 0, wd], m];
}
export function explosionProb(f, model = MODEL) {
  let z = model.intercept; f.forEach((x, i) => { z += model.coef[i] * (x - model.mean[i]) / model.std[i]; });
  return 1 / (1 + Math.exp(-Math.max(-50, Math.min(50, z))));
}

// ---------- proof gate (promotion.py), scored on SPY open/close from LIVE_START ----------
export function liveRows(spx, vix, spy) {
  const days = Object.keys(spx).filter(d => spy[d]).sort(), out = [];
  for (let i = 1; i < days.length; i++) {
    const p = days[i - 1], d = days[i];
    if (d < LIVE_START || !vix[p]) continue;
    const pc = spx[p][3], m = expectedMove(pc, vix[p][3]);
    out.push({ d, pc, m, g: (spx[d][0] - pc) / m, spx: spx[d], spyO: spy[d][0], spyC: spy[d][3] });
  }
  return out;
}
export function gate(spx, vix, spy) {
  const rows = liveRows(spx, vix, spy);
  const pnl = rows.filter(r => Math.abs(r.g) >= TRADE_K).map(r => 10 * Math.sign(r.g) * (r.spyC - r.spyO) - COST_PT);
  const w = pnl.filter(x => x > 0).length, [lo, hi] = meanCi(pnl);
  const trade = { n: pnl.length, wins: w, total: Math.round(pnl.reduce((a, b) => a + b, 0)),
    status: pnl.length >= MIN_TRADES && lo > 0 && wilson(w, pnl.length)[0] > 0.5 ? 'PROVEN' : pnl.length >= MIN_TRADES && hi < 0 ? 'FAILED' : 'TESTING' };
  const hits = rows.filter(r => Math.abs(r.g) >= DIR_K && r.spyC !== r.spyO).map(r => (r.spyC > r.spyO) === (r.g > 0));
  const [dlo, dhi] = wilson(hits.filter(Boolean).length, hits.length);
  const direction = { n: hits.length, hits: hits.filter(Boolean).length, status: hits.length >= MIN_DIR && dlo > 0.5 ? 'PROVEN' : hits.length >= MIN_DIR && dhi < 0.55 ? 'FAILED' : 'TESTING' };
  const lv = (test, claim) => { const k = rows.filter(test).length, [a, b] = wilson(k, rows.length); return { n: rows.length, hits: k, claim, ok: rows.length < 20 || (a * 100 <= claim && claim <= b * 100) }; };
  const levels = { high: lv(r => r.spx[1] >= r.pc + K_HIGH * r.m, HIT_HIGH), low: lv(r => r.spx[2] <= r.pc - K_LOW * r.m, HIT_LOW),
    range: lv(r => r.pc - r.m <= r.spx[2] && r.spx[1] <= r.pc + r.m, RANGE_RATE) };
  const days = Object.keys(spx).filter(d => spy[d]).sort(), rp = [];
  for (let i = 3; i < days.length - 1; i++) {
    if (days[i] < LIVE_START) continue;
    if ([0, 1, 2].every(k => spx[days[i - k]][3] < spx[days[i - k - 1]][3])) rp.push(10 * (spy[days[i + 1]][3] - spy[days[i]][3]) - COST_PT);
  }
  const rw = rp.filter(x => x > 0).length, [rlo, rhi] = meanCi(rp);
  const reversal = { n: rp.length, wins: rw, total: Math.round(rp.reduce((a, b) => a + b, 0)),
    status: rp.length >= MIN_TRADES && rlo > 0 && wilson(rw, rp.length)[0] > 0.5 ? 'PROVEN' : rp.length >= MIN_TRADES && rhi < 0 ? 'FAILED' : 'TESTING' };
  return { sessions: rows.length, trade, direction, levels, reversal };
}
export function recordLine(g) {
  const t = g.trade, rv = g.reversal, d = g.direction, L = g.levels;
  let tr = t.n ? `الصفقة ${t.wins}/${t.n} رابحة، ${t.total >= 0 ? '+' : ''}${t.total} نقطة` : 'الصفقة لم تتفعّل بعد';
  if (rv.n) tr += ` | الارتداد ${rv.wins}/${rv.n}، ${rv.total >= 0 ? '+' : ''}${rv.total} نقطة`;
  const lvl = [['high', 'القمة'], ['low', 'القاع'], ['range', 'المدى']].map(([k, n]) => `${n} ${L[k].hits}/${L[k].n} (المعلن ${L[k].claim}%)${L[k].ok ? '' : ' ⚠️'}`).join(' | ');
  return `📒 السجل الحي منذ ${LIVE_START} (${g.sessions} جلسة، أسعار SPY): ${tr} | الاتجاه من الافتتاح ${d.hits}/${d.n} | ${lvl}`;
}


// ---------- breakout detector: 30-min box break with a volume surge (research/filters_20261124/squeeze.py) ----------
// SPY 5m: box = high/low of the 6 bars ending at bar i (10:00-15:00 NY). Entry: stop order 1 tick beyond the box on the
// first break within 6 bars whose volume >= 2.0 x the prior 20-bar average; stop = other side of the box; target = 1.5 x
// risk; exit after 12 bars or at the close. Research at 2.0x: SPY train +0.12 R, test +0.23 R (n=22); 10 untouched stocks
// +0.08 R (n=465), +0.23 R after 11-13 (n=49); without the volume surge about −0.05 to −0.09 R. Unproven: scored live every evening.
export const BO = { N: 6, K: 6, H: 12, T: 1.5, VOL: 2.0, TICK: 0.01 };   // 2.0x since 2026-11-27 (research/breakout_vol_20261127)
const atr20 = (B, i) => { let s = 0; for (let j = i - 19; j <= i; j++) s += Math.max(B[j].h - B[j].l, Math.abs(B[j].h - B[j - 1].c), Math.abs(B[j].l - B[j - 1].c)); return s / 20; };
export function breakoutTrades(B) {
  // B: one session of completed 5m bars {t, o, h, l, c, v} in time order. Same loop as squeeze.py events(vol_conf=True).
  const out = [], { N, K, H, T, VOL, TICK } = BO;
  let i = 21;   // the research needs 21 bars of the same session before the box (signals from ~11:15 NY)
  while (i < B.length - 1) {
    const m = ny(B[i].t).mins;
    if (m < 600 || m > 900) { i++; continue; }
    const box = B.slice(i - N + 1, i + 1), hi = Math.max(...box.map(b => b.h)), lo = Math.min(...box.map(b => b.l));
    if (!(atr20(B, i) > 0)) { i++; continue; }
    let done = false;
    for (let j = i + 1; j < Math.min(i + 1 + K, B.length); j++) {
      const up = B[j].h > hi, dn = B[j].l < lo;
      if (up && dn) break;
      if (!up && !dn) continue;
      const avgV = B.slice(j - 20, j).reduce((a, b) => a + b.v, 0) / 20;
      if (!avgV || B[j].v < VOL * avgV) break;
      const d = up ? 1 : -1, e = up ? hi + TICK : lo - TICK, risk = up ? e - lo + TICK : hi + TICK - e;
      const stop = e - d * risk, tgt = e + d * T * risk;
      let R = null, k = j, exitT = B[j].t;
      if (d > 0 ? B[j].l <= stop : B[j].h >= stop) R = -1; else if (d > 0 ? B[j].h >= tgt : B[j].l <= tgt) R = T;
      while (R === null) {
        k++;
        if (k >= B.length || k > j + H) { R = d * (B[k - 1].c - e) / risk; exitT = B[k - 1].t; break; }
        const hs = d > 0 ? B[k].l <= stop : B[k].h >= stop, ht = d > 0 ? B[k].h >= tgt : B[k].l <= tgt;
        if (hs) R = -1; else if (ht) R = T;
        exitT = B[k].t;
      }
      out.push({ entryT: B[j].t, d, e, stop, tgt, risk, R, volX: B[j].v / avgV, exitT, open: k >= B.length });
      i = k; done = true; break;
    }
    if (!done) i++;
  }
  return out;
}
export async function spySession(now, fetcher, range = '1d') {
  const r = await chart('SPY', `interval=5m&range=${range}`, fetcher), q = r.indicators.quote[0];
  return r.timestamp.map((ts, i) => ({ t: new Date(ts * 1000), o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume[i] || 0 }))
    .filter(b => b.c != null && b.t.getTime() + 5 * 6e4 <= now.getTime() && ny(b.t).mins >= 570 && ny(b.t).mins < closeMins(ny(b.t).iso));
}
const BYDAY = B => B.reduce((m, b) => { (m[ny(b.t).iso] ||= []).push(b); return m; }, {});
export async function breakoutAlert(now, fetcher = fetch) {
  const t = ny(now);
  if (!isSession(t.iso)) return null;
  const B = BYDAY(await spySession(now, fetcher))[t.iso] || [];
  // alert only for an entry on the bar that completed in the last 5 minutes: each signal is sent exactly once
  const fresh = breakoutTrades(B).filter(x => { const end = x.entryT.getTime() + 5 * 6e4; return end > now.getTime() - 6 * 6e4 && end <= now.getTime() - 6e4; });
  if (!fresh.length) return null;
  const x = fresh[0], spx = v => (v * 10).toFixed(0);
  return [`🎯 كسر صندوق مع حجم — ${x.d > 0 ? 'شراء 📈' : 'بيع 📉'} (كاشف تحت الاختبار)`,
    `SPY: دخول ${x.e.toFixed(2)} | وقف ${x.stop.toFixed(2)} | هدف ${x.tgt.toFixed(2)} (1.5 × المخاطرة)`,
    `≈ SPX: دخول ${spx(x.e)} | وقف ${spx(x.stop)} | هدف ${spx(x.tgt)}`,
    `الحجم ${x.volX.toFixed(1)}× المتوسط | شمعة ${riyadh(x.entryT)}–${riyadh(new Date(x.entryT.getTime() + 3e5))} الرياض | خروج بعد ساعة كحد أقصى`,
    'البحث: +0.10R على بيانات جديدة (54% ربح)، غير مثبت إحصائيًا بعد. حجم صغير، ويُقيَّم كل مساء.'].join('\n');
}
export function breakoutRecord(B) {
  const days = BYDAY(B), all = [];
  for (const d of Object.keys(days).sort()) if (d >= LIVE_START) for (const x of breakoutTrades(days[d])) if (!x.open) all.push(x);
  const n = all.length, w = all.filter(x => x.R > 0).length, sum = all.reduce((a, x) => a + x.R, 0);
  return { n, w, sum };
}

// ---------- jobs ----------
async function context(now, fetcher, session) {
  const start = addDays(session, -90);
  const [spx, vixd, spy] = await Promise.all([daily('^GSPC', start, now, fetcher), daily('^VIX', start, now, fetcher), daily('SPY', start, now, fetcher)]);
  const vix = Object.fromEntries(Object.entries(vixd).map(([d, v]) => [d, v[3]]));
  return { spx, vixd, vix, spy };
}

export async function morning(now, fetcher = fetch) {
  const t = ny(now), session = t.iso;
  if (!isSession(session)) return null;
  const { spx, vixd, vix, spy } = await context(now, fetcher, session);
  const days = Object.keys(spx).filter(d => d < session && vix[d]).sort();
  const pd = days.at(-1), pc = spx[pd][3], v = vix[pd], m = expectedMove(pc, v);
  if (pd !== prevSession(session)) throw new Error(`stale daily data: last ${pd}, expected ${prevSession(session)}`);
  // futures move since the previous session's close (ES=F 5m incl. pre-market, ~10 min delayed)
  let mv = null;
  try {
    const b = await bars5m('ES=F', '5d', now, fetcher, true);
    const ref = nyInstant(pd, closeMins(pd) - 5), refB = b.filter(x => x.t <= ref).at(-1), last = b.at(-1);
    if (refB && last && last.t > ref && now - last.t < 45 * 6e4) mv = { r: last.c / refB.c - 1, t: last.t };
  } catch (e) { console.log('ES failed', e.message); }
  const lines = [`📊 SPX اليوم — ${session}`];
  let anchor = pc;
  if (mv) {
    anchor = pc * (1 + mv.r);
    const g = (anchor - pc) / m, [key, label, conf] = gapDirection(g), [upO, dnO] = openOdds(g);
    lines.push(key === 'flat' ? `الاتجاه: ${label} — من الافتتاح: صعود ${upO}% | هبوط ${dnO}%`
      : `الاتجاه: ${label} — ${key === 'up' ? upO : dnO}% من سعر الافتتاح (و${conf}% أن يغلق ${key === 'up' ? 'فوق' : 'تحت'} إغلاق أمس، وهذا تصنعه الفجوة غالبًا)`);
    const [l1, l2] = OPEN_LEVELS;
    lines.push(`القمة: سيصل على الأقل إلى ${fmt(anchor + l1[0] * m)} (${l1[1]}%)، ومحتمل ${fmt(anchor + l2[0] * m)} (${l2[1]}%)`,
      `القاع: سينزل على الأقل إلى ${fmt(anchor - l1[0] * m)} (${l1[2]}%)، ومحتمل ${fmt(anchor - l2[0] * m)} (${l2[2]}%)`,
      `الافتتاح المتوقع: ${fmt(anchor)} (العقود الآجلة ${pct(100 * mv.r)} منذ إغلاق أمس، آخر قراءة ${riyadh(mv.t)} الرياض)`);
  } else {
    lines.push(`الاتجاه: صاعد 📈 (يصيب ${UP_RATE}% من الأيام) — العقود الآجلة غير متاحة الآن`,
      `القمة: سيصل على الأقل إلى ${fmt(pc + K_HIGH * m)} (${HIT_HIGH}%)`, `القاع: سينزل على الأقل إلى ${fmt(pc - K_LOW * m)} (${HIT_LOW}%)`);
  }
  lines.push(`أقصى مدى مرجّح: ${fmt(pc - m)} – ${fmt(pc + m)} (${RANGE_RATE}%)`);
  if (mv) {
    try {
      const rows = days.filter(d => spx[d]).slice(-25).map(d => [d, ...spx[d]]);
      const [f, mm] = explosionFeatures(session, rows, vix, anchor), p = explosionProb(f), tier = MODEL.tiers.find(x => p >= x.min_p);
      if (tier) lines.push(`⚡ خطر حركة قوية اليوم: ${tier.label} — حركة ≥ ${Math.round(MODEL.k_explode * mm)} نقطة من الافتتاح تحدث في ${tier.rate}% من مثل هذه الأيام مقابل ${MODEL.base_rate}% عادة`);
    } catch (e) { console.log('explosion failed', e.message); }
  }
  let gt = null;
  try { gt = gate(spx, vixd, spy); } catch (e) { console.log('gate failed', e.message); }
  const st = gt?.trade.status || 'TESTING';
  const lv = [`• افتتاح ≥ ${fmt(pc + TRADE_K * m)} ← شراء عند الافتتاح، خروج عند الإغلاق`, `• افتتاح ≤ ${fmt(pc - TRADE_K * m)} ← بيع عند الافتتاح، خروج عند الإغلاق`, '• بينهما ← لا صفقة'];
  if (st === 'FAILED') lines.push(`🎯 صفقة الفجوة أُوقفت تلقائيًا: خسرت في السجل الحي (${gt.trade.wins}/${gt.trade.n} رابحة، ${gt.trade.total} نقطة على SPY).`);
  else if (st === 'PROVEN') lines.push(`🎯 التوصية (مثبتة في السجل الحي: ${gt.trade.wins}/${gt.trade.n} رابحة):`, ...lv, 'التنفيذ على المؤشر نفسه (SPY/MES/ES)، لا بشراء أوبشن 0DTE.');
  else lines.push('🎯 صفقة اليوم المشروطة (اختبار حي، غير مثبتة):', ...lv, 'الدليل: المؤشر 2020–2026 ربح 59% (+8.7 نقطة/صفقة)، لكن SPY الفعلي 2024–2026 خسر −2.2. بحجم صغير فقط، وليس بشراء أوبشن 0DTE.');
  const c3 = days.slice(-3).map(d => spx[d][3]);
  if (c3.length === 3 && c3[2] < c3[1] && c3[1] < c3[0] && gt?.reversal.status !== 'FAILED') {
    lines.push(`🔁 إشارة ارتداد${gt?.reversal.status === 'PROVEN' ? ' (مثبتة حيًا)' : ''}: إن أغلق اليوم تحت ${fmt(pc)} (ثالث هبوط متتالٍ) ← شراء عند الإغلاق والخروج عند إغلاق الغد.`,
      '   تاريخيًا 1990–2026 ربحت 57–64% في كل عقد. تفوقها على مجرد الشراء ضعيف في العقود الهادئة. تُقاس حيًا.');
  }
  if (gt) lines.push(recordLine(gt));
  const openAt = nyInstant(session, 570);
  lines.push('', `إغلاق أمس ${pc.toFixed(2)} | VIX ${v.toFixed(1)} | الافتتاح ${riyadh(openAt)} الرياض`);
  if (EARLY_CLOSE.has(session)) lines.push(`⚠️ جلسة قصيرة: الإغلاق 13:00 نيويورك = ${riyadh(nyInstant(session, 780))} الرياض`);
  const nx = nextSession(session), closed = [];
  for (let d = addDays(session, 1); d < nx; d = addDays(d, 1)) if (weekday(d) % 6 !== 0) closed.push(d);
  if (closed.length) lines.push(`🏖️ السوق مغلق (عطلة رسمية): ${closed.join('، ')} — الجلسة التالية ${nx}`);
  lines.push('المصدر Yahoo (متأخر). نسب تاريخية، ليست ضمانًا.');
  return lines.join('\n');
}

export async function firstHour(now, fetcher = fetch) {
  const t = ny(now), session = t.iso;
  if (!isSession(session)) return null;
  const b = (await bars5m('^GSPC', '1d', now, fetcher)).filter(x => { const n = ny(x.t); return n.iso === session && n.mins >= 570 && n.mins < 630; });
  if (b.length < 12) throw new Error(`first hour incomplete: ${b.length}/12 five-minute bars`);
  const start = addDays(session, -10), [spx, vix] = await Promise.all([daily('^GSPC', start, now, fetcher), daily('^VIX', start, now, fetcher)]);
  const pd = prevSession(session);
  if (!spx[pd] || !vix[pd]) throw new Error('previous close unavailable');
  const m = expectedMove(spx[pd][3], vix[pd][3]), h1 = Math.max(...b.map(x => x.h)), l1 = Math.min(...b.map(x => x.l)), last = b.at(-1).c;
  const r1 = (h1 - l1) / m, tier = r1 < R1_CUTS[0] ? 0 : r1 < R1_CUTS[1] ? 1 : 2;
  return [
    `⏱️ SPX بعد الساعة الأولى — ${session}`,
    `الساعة الأولى: أعلى ${fmt(h1)} | أدنى ${fmt(l1)} | الآن ${fmt(last)}`,
    `🔺 القمة: تتجاوز ${fmt(h1)} ← ${P_BREAK_UP}% | الحد المرجّح ${fmt(h1 + EXT_UP[0] * m)} (${COV_UP[0]}%) | الأقصى ${fmt(h1 + EXT_UP[1] * m)} (${COV_UP[1]}%)`,
    `🔻 القاع: يكسر ${fmt(l1)} ← ${P_BREAK_DN}% | الحد المرجّح ${fmt(l1 - EXT_DN[0] * m)} (${COV_DN[0]}%) | الأقصى ${fmt(l1 - EXT_DN[1] * m)} (${COV_DN[1]}%)`,
    `أحد طرفي الساعة الأولى يبقى قمة أو قاع اليوم في ${P_ONE_HOLDS}% من الأيام.`,
    `خطر حركة كبيرة بقية اليوم (≥ ${Math.round(BIG_K * m)} نقطة من الآن): ${['منخفض', 'عادي', 'مرتفع ⚡'][tier]} — ${BIG_RATES[tier]}% (الساعة الأولى ${r1.toFixed(2)} من الحركة المتوقعة)`,
    '', `المصدر Yahoo (قد يتأخر). نسب 2025–2026 خارج عينة التدريب، ليست ضمانًا.`,
  ].join('\n');
}

export async function evening(now, fetcher = fetch) {
  const t = ny(now), session = t.iso;
  if (!isSession(session)) return null;
  const { spx, vixd, vix, spy } = await context(now, fetcher, session);
  if (!spx[session]) throw new Error(`today's daily bar not available yet for ${session}`);
  const pd = prevSession(session), pc = spx[pd][3], m = expectedMove(pc, vix[pd]);
  const [o, h, l, c] = spx[session], g = (o - pc) / m, ok = b => (b ? '✅' : '❌');
  const [key, label] = gapDirection(g);
  const lines = [`🌙 نتيجة اليوم — ${session}`,
    `الافتتاح ${fmt(o)} | القمة ${fmt(h)} | القاع ${fmt(l)} | الإغلاق ${fmt(c)} (${pct(100 * (c / pc - 1))})`];
  if (key !== 'flat') lines.push(`الاتجاه ${label} من الافتتاح: ${ok(key === 'up' ? c > o : c < o)}`);
  const [l1, l2] = OPEN_LEVELS;
  lines.push(`القمة ≥ ${fmt(o + l1[0] * m)} (${l1[1]}%): ${ok(h >= o + l1[0] * m)} | ≥ ${fmt(o + l2[0] * m)} (${l2[1]}%): ${ok(h >= o + l2[0] * m)}`,
    `القاع ≤ ${fmt(o - l1[0] * m)} (${l1[2]}%): ${ok(l <= o - l1[0] * m)} | ≤ ${fmt(o - l2[0] * m)} (${l2[2]}%): ${ok(l <= o - l2[0] * m)}`,
    `المدى ${fmt(pc - m)} – ${fmt(pc + m)} (${RANGE_RATE}%): ${ok(l >= pc - m && h <= pc + m)}`,
    `حركة قوية (≥ ${Math.round(MODEL.k_explode * m)} نقطة من الافتتاح): ${Math.abs(c - o) >= MODEL.k_explode * m ? 'حدثت' : 'لم تحدث'}`);
  if (Math.abs(g) >= TRADE_K && spy[session]) {
    const s = Math.sign(g), pnl = 10 * s * (spy[session][3] - spy[session][0]) - COST_PT;
    lines.push(`🎯 الصفقة المشروطة: ${s > 0 ? 'شراء' : 'بيع'} ← ${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)} نقطة على SPY بعد التكلفة ${ok(pnl > 0)}`);
  } else lines.push('🎯 الصفقة المشروطة: لم تتفعّل (الافتتاح بين المستويين)');
  try {   // first-hour forecast, recomputed from today's 5m bars
    const b = (await bars5m('^GSPC', '1d', now, fetcher)).filter(x => { const n = ny(x.t); return n.iso === session && n.mins >= 570 && n.mins < 630; });
    if (b.length >= 12) {
      const h1 = Math.max(...b.map(x => x.h)), lo1 = Math.min(...b.map(x => x.l));
      lines.push(`⏱️ الساعة الأولى: القمة المرجّحة ${ok(h <= h1 + EXT_UP[0] * m)} الأقصى ${ok(h <= h1 + EXT_UP[1] * m)} | القاع المرجّح ${ok(l >= lo1 - EXT_DN[0] * m)} الأقصى ${ok(l >= lo1 - EXT_DN[1] * m)}`);
    }
  } catch (e) { console.log('first hour scoring failed', e.message); }
  const days = Object.keys(spx).filter(d => d <= session).sort(), i = days.indexOf(session);
  if (i >= 4 && [1, 2, 3].every(k => spx[days[i - k]][3] < spx[days[i - k - 1]][3]) && spy[session] && spy[days[i - 1]]) {
    const pnl = 10 * (spy[session][3] - spy[days[i - 1]][3]) - COST_PT;
    lines.push(`🔁 إشارة الارتداد (شراء إغلاق أمس): ${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)} نقطة ${ok(pnl > 0)}`);
  }
  try {
    const B5 = await spySession(now, fetcher, '60d'), today = breakoutTrades(BYDAY(B5)[session] || []), rec = breakoutRecord(B5);
    lines.push(today.length ? `📦 كسر الصندوق اليوم: ${today.map(x => `${x.d > 0 ? 'شراء' : 'بيع'} ${riyadh(x.entryT)} ← ${x.R >= 0 ? '+' : ''}${x.R.toFixed(2)}R`).join(' | ')}` : '📦 كسر الصندوق اليوم: لا إشارات');
    if (rec.n) lines.push(`📦 سجل كاشف الكسر منذ ${LIVE_START}: ${rec.w}/${rec.n} رابحة، مجموع ${rec.sum >= 0 ? '+' : ''}${rec.sum.toFixed(1)}R`);
  } catch (e) { console.log('breakout scoring failed', e.message); }
  try { lines.push('', recordLine(gate(spx, vixd, spy))); } catch (e) { console.log('gate failed', e.message); }
  lines.push('المصدر Yahoo يومي (متأخر).');
  return lines.join('\n');
}

// ---------- delivery: Telegram only ----------
export function chunks(text, limit = 3900) {
  const out = []; let cur = '';
  for (const line of text.split('\n')) {
    if (cur && cur.length + line.length + 1 > limit) { out.push(cur); cur = ''; }
    cur = cur ? cur + '\n' + line : line;
    while (cur.length > limit) { out.push(cur.slice(0, limit)); cur = cur.slice(limit); }
  }
  if (cur.trim()) out.push(cur);
  return out;
}
export async function telegram(env, text, fetcher = fetch) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) throw new Error('Telegram secrets missing');
  for (const part of chunks(text)) {
    let ok = false;
    for (let i = 0; i < 3 && !ok; i++) {
      const r = await fetcher(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: part, disable_web_page_preview: true }) });
      ok = r.ok;
      if (!ok) await new Promise(res => setTimeout(res, 2000 * (i + 1)));
    }
    if (!ok) throw new Error('Telegram send failed');
  }
}

// ---------- scheduling: one 10-minute cron, each job on its New York time ----------
export function dueJobs(now) {
  const t = ny(now), jobs = [];
  if (!isSession(t.iso)) return jobs;
  const at = target => t.mins >= target && t.mins < target + 5;
  if (at(8 * 60 + 40)) jobs.push('morning');            // 08:40 NY: after the 08:30 data releases, 50 min before the open
  if (at(10 * 60 + 40)) jobs.push('firsthour');         // 10:40 NY: first hour complete (+ data delay)
  if (t.mins >= 600 && t.mins <= closeMins(t.iso) + 5) jobs.push('breakout');   // every in-session tick
  if (at(closeMins(t.iso) + 20)) jobs.push('evening');  // 20 min after the close (13:00 on early-close days)
  return jobs;
}
const JOBS = { morning, firsthour: firstHour, evening, breakout: breakoutAlert };

async function runJob(job, env, now, send = true) {
  try {
    const msg = await JOBS[job](now);
    if (msg && send) await telegram(env, msg);
    return msg || 'NO_SESSION';
  } catch (e) {
    console.log(`${job} failed: ${e.message}`);   // data failures are logged only: no error messages to Telegram
    return `FAILED: ${e.message}`;
  }
}

export default {
  async scheduled(event, env, ctx) {
    const now = new Date(event.scheduledTime);
    if (CAL_LAST < ny(now).iso) console.log('NYSE calendar table needs the next year');
    for (const job of dueJobs(now)) ctx.waitUntil(runJob(job, env, now));
  },
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname === '/run' && env.RUN_KEY && u.searchParams.get('key') === env.RUN_KEY && JOBS[u.searchParams.get('job')]) {
      const out = await runJob(u.searchParams.get('job'), env, new Date(), u.searchParams.get('send') !== '0');
      return new Response(out, { headers: { 'content-type': 'text/plain; charset=utf-8' } });
    }
    return new Response('suhail-hunter ok', { headers: { 'content-type': 'text/plain' } });
  },
};
