import test from 'node:test';
import assert from 'node:assert/strict';
import * as W from '../src/index.js';

// ----- synthetic Yahoo: daily bars for every session up to `last`, 5m bars for one session -----
const NYOPEN = iso => W.nyInstant(iso, 570);
function sessions(from, to) { const out = []; for (let d = from; d <= to; d = new Date(Date.parse(d + 'T12:00:00Z') + 864e5).toISOString().slice(0, 10)) if (W.isSession(d)) out.push(d); return out; }
function dailyJson(days, f) {
  return { chart: { result: [{ timestamp: days.map(d => NYOPEN(d).getTime() / 1000), indicators: { quote: [{
    open: days.map((d, i) => f(i)[0]), high: days.map((d, i) => f(i)[1]), low: days.map((d, i) => f(i)[2]), close: days.map((d, i) => f(i)[3]) }] } }] } };
}
function fiveJson(points) {
  return { chart: { result: [{ timestamp: points.map(p => p.t.getTime() / 1000), indicators: { quote: [{
    high: points.map(p => p.h), low: points.map(p => p.l), close: points.map(p => p.c) }] } }] } };
}
function fakeFetch({ upto, today, esMove = -0.006, closes = i => 6800 + 2 * i }) {
  const days = sessions('2026-08-01', upto);
  return async (url) => {
    const sym = decodeURIComponent(url.split('/chart/')[1].split('?')[0]);
    let body;
    if (url.includes('interval=1d')) {
      const f = sym === '^VIX' ? () => [16, 17, 15, 16] : sym === 'SPY' ? i => [closes(i) / 10, closes(i) / 10 + 2, closes(i) / 10 - 2, closes(i) / 10 + 0.3]
        : i => [closes(i) - 5, closes(i) + 30, closes(i) - 30, closes(i)];
      body = dailyJson(days, f);
    } else if (sym === 'ES=F') {
      const prev = W.prevSession(today), ref = W.nyInstant(prev, 955), pts = [];
      for (let k = 0; k < 200; k++) { const t = new Date(ref.getTime() + k * 3e5); pts.push({ t, h: 1, l: 1, c: k === 0 ? 7000 : 7000 * (1 + esMove) }); }
      body = fiveJson(pts);
    } else {
      const pts = []; for (let k = 0; k < 30; k++) { const t = new Date(NYOPEN(today).getTime() + k * 3e5); pts.push({ t, h: 7000 + k, l: 6990 - k, c: 6995 }); }
      body = fiveJson(pts);
    }
    return { ok: true, json: async () => body };
  };
}

test('calendar: holidays, early close, DST-safe New York instants', () => {
  assert.equal(W.isSession('2026-11-26'), false);
  assert.equal(W.isSession('2026-11-27'), true);
  assert.equal(W.closeMins('2026-11-27'), 780);
  assert.equal(W.prevSession('2026-11-27'), '2026-11-25');
  assert.equal(W.nextSession('2026-12-24'), '2026-12-28');
  assert.equal(W.nyInstant('2026-11-24', 570).toISOString(), '2026-11-24T14:30:00.000Z');   // EST
  assert.equal(W.nyInstant('2026-07-01', 570).toISOString(), '2026-07-01T13:30:00.000Z');   // EDT
  assert.equal(W.nyInstant('2026-03-09', 570).toISOString(), '2026-03-09T13:30:00.000Z');   // day after DST start
});

test('dueJob fires each job once per day at its New York time', () => {
  const at = (iso, m) => W.nyInstant(iso, m);
  assert.equal(W.dueJob(at('2026-11-24', 520)), 'morning');
  assert.equal(W.dueJob(at('2026-11-24', 529)), 'morning');
  assert.equal(W.dueJob(at('2026-11-24', 530)), null);
  assert.equal(W.dueJob(at('2026-11-24', 640)), 'firsthour');
  assert.equal(W.dueJob(at('2026-11-24', 980)), 'evening');
  assert.equal(W.dueJob(at('2026-11-27', 800)), 'evening');          // early close 13:00 -> 13:20
  assert.equal(W.dueJob(at('2026-11-26', 520)), null);              // Thanksgiving
  let n = 0; for (let m = 0; m < 1440; m += 10) if (W.dueJob(at('2026-11-24', m))) n++;
  assert.equal(n, 3);
});

test('direction buckets and tradable odds match the Python tables', () => {
  assert.deepEqual(W.gapDirection(-0.6), ['down', 'هابط 📉', 90]);
  assert.deepEqual(W.gapDirection(0.0)[0], 'flat');
  assert.deepEqual(W.openOdds(-0.6), [41, 59]);
  assert.deepEqual(W.openOdds(0.7), [61, 39]);
});

test('explosion probability equals the Python model on a reference vector', () => {
  // f = model means -> z = intercept
  const p = W.explosionProb([0.02117249568994317, 0.2044527212204415, 18.510666511385867, 0.3277359860781731, 1.4028110410137073, 0.9144511202362436, 0.49673725835317767, 0.9208171913091644, 0.9344621022574651, 0.5438681531749879, 2.0181774115365974]);
  assert.ok(Math.abs(p - 1 / (1 + Math.exp(1.287491762697664))) < 1e-12);
});

test('morning message: gap call, levels, trade, record, footer', async () => {
  const now = W.nyInstant('2026-11-24', 520);
  const msg = await W.morning(now, fakeFetch({ upto: '2026-11-23', today: '2026-11-24' }));
  for (const s of ['SPX اليوم — 2026-11-24', 'الاتجاه: هابط', 'من سعر الافتتاح', 'القمة: سيصل', 'أقصى مدى', 'صفقة اليوم المشروطة', 'السجل الحي', 'الافتتاح 17:30 الرياض'])
    assert.ok(msg.includes(s), s);
});

test('morning refuses stale daily data instead of sending wrong levels', async () => {
  const now = W.nyInstant('2026-11-24', 520);
  await assert.rejects(W.morning(now, fakeFetch({ upto: '2026-11-19', today: '2026-11-24' })), /stale/);
});

test('reversal line appears after two lower closes', async () => {
  const now = W.nyInstant('2026-11-24', 520);
  const msg = await W.morning(now, fakeFetch({ upto: '2026-11-23', today: '2026-11-24', closes: i => 7000 - 3 * i }));
  assert.ok(msg.includes('إشارة ارتداد'));
});

test('first hour: levels from 12 complete bars; incomplete hour fails closed', async () => {
  const msg = await W.firstHour(W.nyInstant('2026-11-24', 640), fakeFetch({ upto: '2026-11-23', today: '2026-11-24' }));
  assert.ok(msg.includes('أعلى 7,011') && msg.includes('أدنى 6,979') && msg.includes('(75%)'));
  await assert.rejects(W.firstHour(W.nyInstant('2026-11-24', 600), fakeFetch({ upto: '2026-11-23', today: '2026-11-24' })), /incomplete/);
});

test('evening scores the day and the live record', async () => {
  const msg = await W.evening(W.nyInstant('2026-11-24', 980), fakeFetch({ upto: '2026-11-24', today: '2026-11-24' }));
  for (const s of ['نتيجة اليوم — 2026-11-24', 'القمة ≥', 'المدى', 'الصفقة المشروطة', 'الساعة الأولى', 'السجل الحي']) assert.ok(msg.includes(s), s);
});

test('gate statuses follow the preregistered rules', () => {
  const days = sessions('2026-11-13', '2027-03-31'), spx = {}, vix = {}, spy = {};
  let pc = 7000, sp = 700;
  days.forEach((d, i) => {
    const s = i % 2 ? 1 : -1, o = pc + s * 0.6 * W.expectedMove(pc, 16);
    spx[d] = [o, o + 20, o - 20, pc]; vix[d] = [16, 16, 16, 16];
    const so = sp + s * 3; spy[d] = [so, so, so, so + s * 1.0]; sp = so + s;
  });
  const g = W.gate(spx, vix, spy);
  assert.equal(g.trade.status, 'PROVEN');
  assert.ok(g.trade.n >= 30);
  assert.ok(W.recordLine(g).includes('السجل الحي'));
});

test('telegram chunks stay under the limit and keep all text', () => {
  const text = ('سطر '.repeat(300) + '\n').repeat(10);
  const parts = W.chunks(text);
  assert.ok(parts.every(p => p.length <= 3900));
  assert.equal(parts.join('\n').replace(/\n/g, ''), text.replace(/\n/g, ''));
});

test('telegram sends with retries and fails loudly when secrets are missing', async () => {
  const calls = [];
  await W.telegram({ TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: 'c' }, 'hi', async (u, o) => { calls.push(JSON.parse(o.body)); return { ok: true }; });
  assert.deepEqual(calls, [{ chat_id: 'c', text: 'hi', disable_web_page_preview: true }]);
  await assert.rejects(W.telegram({}, 'x'), /secrets missing/);
});
