"""Pre-open SPX daily range alert (Telegram). Expected 1-day move = prior close x (VIX/100) / sqrt(252).
Historical coverage 2010-2026 (both daily high and low inside the band): +/-1 move 68.7%, +/-1.5 moves 90.1%.
No direction forecast: SPX closed up on 54.5% of days since 2010 (base rate, not a signal). Data: Yahoo daily (delayed)."""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY, RIYADH = ZoneInfo('America/New_York'), ZoneInfo('Asia/Riyadh')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')


class DataUnavailable(Exception):
    """Yahoo did not answer after all retries; the run ends cleanly and a later run retries."""


def yahoo_chart(symbol, query, tries=4, sleep=time.sleep):
    """Yahoo chart JSON with retries across both public hosts (it returned 502s and read timeouts on 2026-11-19)."""
    last = None
    for i in range(tries):
        host = ('query1', 'query2')[i % 2]
        url = f'https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?{query}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-range-alert)'})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())['chart']['result'][0]
        except (OSError, ValueError, KeyError, TypeError) as e:   # URLError/HTTPError/timeouts are OSError
            last = e
            print(f'YAHOO_RETRY {symbol} {host} {type(e).__name__}: {e}', file=sys.stderr, flush=True)
            if i < tries-1:
                sleep((5, 15, 30)[min(i, 2)])
    raise DataUnavailable(f'{symbol}: {last}')


def closes(symbol, before, rng='3mo'):
    r = yahoo_chart(symbol, f'interval=1d&range={rng}')
    rows = [(datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date(), c)
            for t, c in zip(r['timestamp'], r['indicators']['quote'][0]['close']) if c]
    return [x for x in rows if x[0] < before]  # completed sessions only


def last_close(symbol, before):
    return closes(symbol, before)[-1]


def realized_vol_21(rows):
    """Annualized close-to-close volatility (%) over the last 21 completed sessions (known before the open)."""
    px = [c for _, c in rows[-22:]]
    rets = [math.log(b/a) for a, b in zip(px, px[1:])]
    return math.sqrt(sum(x*x for x in rets)*252/len(rets))*100


def options_cost_line(vix, rv):
    """VIX minus trailing realized vol. Long-run mean of VIX minus subsequent realized vol, 1990-2026: +4.1 points."""
    p = vix-rv
    label = 'مرتفعة: المشتري يدفع علاوة أعلى من المعتاد' if p > 4.1 else ('عادية' if p >= 0 else 'رخيصة نسبيًا: التقلب الفعلي أعلى من المسعّر')
    return f"تكلفة الأوبشن: VIX {vix:.1f} مقابل تقلب فعلي (21 يوم) {rv:.1f} ← الفارق {p:+.1f} نقطة — {label}"


# Reach probabilities from the open, in units of m (expected 1-day move). k values calibrated on 2010-2019;
# percentages measured on 1727 untouched sessions 2020-01 .. 2026-11-13 (branch research/demark-20261115, research/demark_20261115/minreach.py).
MOVE_FROM_OPEN = [(0.1, 85, 80), (0.25, 63, 60), (0.5, 37, 36)]   # (k, P(high >= open+k*m) %, P(low <= open-k*m) %)
EITHER_SIDE = [(0.25, 96), (0.5, 69)]                              # (k, P(at least one side reaches k*m) %)


def move_lines(m):
    """Arabic lines: how far from the open price usually travels. Direction is not predicted."""
    return ["من سعر الافتتاح (نسب 2020–2026):",
            *[f"• {k*m:.0f} نقطة في اتجاه واحد على الأقل: {p}%" for k, p in EITHER_SIDE],
            *[f"• القمة ≥ الافتتاح +{k*m:.0f}: {ph}% | القاع ≤ الافتتاح −{k*m:.0f}: {pl}%" for k, ph, pl in MOVE_FROM_OPEN],
            "الاتجاه غير معروف مسبقًا، وأسعار الأوبشن تسعّر هذه الحركة عادةً."]


# The daily call. Anchored on the previous close so it is known before the open. k values calibrated on
# 2010-2019; hit rates measured on 1727 untouched sessions 2020-01 .. 2026-11-13 (branch research/demark-20261115,
# research/demark_20261115/minreach.py, anchor pc, p=0.7). Direction: always "up", the best-measured call.
K_HIGH, HIT_HIGH = 0.174, 72     # P(day high >= prev_close + K_HIGH*m)
K_LOW, HIT_LOW = 0.11, 69        # P(day low  <= prev_close - K_LOW*m)
UP_RATE = 54                     # % of sessions closing above the previous close (2010-2026)
RANGE_RATE = 69                  # % of sessions whose high and low both stay within prev_close +- m


def call_levels(pc, m):
    return {'high': pc+K_HIGH*m, 'low': pc-K_LOW*m, 'max_high': pc+m, 'min_low': pc-m}


# Direction from the overnight futures move. g = (implied pre-open level - prev_close) / m. P(close > prev close) per
# bucket, measured on 1726 untouched sessions 2020-01 .. 2026-11-13 with the 09:30 open as the proxy for the pre-open
# level (branch research/gap-direction-20261117, gapdir.py). Sign of the gap: 71% correct vs 54% for always-up.
GAP_BUCKETS = [(-9e9, -0.5, 10), (-0.5, -0.2, 26), (-0.2, -0.05, 40), (-0.05, 0.05, 49),
               (0.05, 0.2, 66), (0.2, 0.5, 76), (0.5, 9e9, 89)]
# Reach from the open (same test sessions): high >= open + k*m / low <= open - k*m.
OPEN_LEVELS = [(0.1, 85, 80), (0.25, 63, 60)]


def gap_direction(g):
    """(key, Arabic label, confidence %) for a gap measured in units of m."""
    for lo, hi, p_up in GAP_BUCKETS:
        if lo <= g < hi:
            if p_up >= 55:
                return 'up', 'صاعد 📈', p_up
            if p_up <= 45:
                return 'down', 'هابط 📉', 100-p_up
            return 'flat', 'محايد ↔️', max(p_up, 100-p_up)


def es_move(session, now):
    """ES futures change since the previous session's close bar, from Yahoo 5m bars (about 10 min delayed).
    Returns (fraction, bar time) or None if unavailable or stale (> 45 min old)."""
    prev = CAL.previous_session(session.isoformat())
    ref_t = CAL.session_close(prev).to_pydatetime() - timedelta(minutes=5)
    r = yahoo_chart('ES=F', 'interval=5m&range=5d&includePrePost=true', tries=2)
    bars = [(datetime.fromtimestamp(t, timezone.utc), c) for t, c in zip(r['timestamp'], r['indicators']['quote'][0]['close']) if c]
    ref = [c for t, c in bars if t <= ref_t]
    last = [(t, c) for t, c in bars if t <= now]
    if not ref or not last or now - last[-1][0] > timedelta(minutes=45) or last[-1][0] <= ref_t:
        return None
    return last[-1][1]/ref[-1]-1, last[-1][0]


def gap_call(pc, m, move):
    a = pc*(1+move)
    key, label, conf = gap_direction((a-pc)/m)
    return {'method': 'gap', 'anchor': a, 'direction': key, 'label': label, 'conf': conf,
            'levels': [{'k': k, 'high': a+k*m, 'low': a-k*m, 'p_high': ph, 'p_low': pl} for k, ph, pl in OPEN_LEVELS],
            'range': [pc-m, pc+m]}


def calendar_notes(session):
    """Arabic notes from the official NYSE calendar: early close today, market closed on the next weekday(s)."""
    notes = []
    close = CAL.session_close(session.isoformat()).to_pydatetime()
    if close.astimezone(NY).hour < 16:
        notes.append(f"⚠️ جلسة قصيرة: الإغلاق {close.astimezone(NY).strftime('%H:%M')} نيويورك = "
                     f"{close.astimezone(RIYADH).strftime('%H:%M')} الرياض")
    nxt = CAL.date_to_session((session+timedelta(days=1)).isoformat(), direction='next').date()
    closed = [session+timedelta(days=k) for k in range(1, (nxt-session).days) if (session+timedelta(days=k)).weekday() < 5]
    if closed:
        notes.append(f"🏖️ السوق مغلق (عطلة رسمية): {'، '.join(d.isoformat() for d in closed)} — الجلسة التالية {nxt.isoformat()}")
    return notes


def build(now=None, force=False):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date()
    if CAL.is_session(today.isoformat()):
        session = today
    elif force:
        session = CAL.date_to_session(today.isoformat(), direction='next').date()
    else:
        return None
    opening = CAL.session_open(session.isoformat()).to_pydatetime()
    if now > opening and not force:
        return 'LATE'   # a pre-open call that arrives after the open is useless; never send it unforced
    spx_rows = closes('^GSPC', session)
    (d, spx), (dv, vix) = spx_rows[-1], last_close('^VIX', session)
    rv = realized_vol_21(spx_rows)
    m = spx*vix/100/math.sqrt(252)
    late = now > opening
    try:
        mv = es_move(session, now)
    except Exception as ex:  # noqa: BLE001  (futures are optional; fall back to the base call)
        print('ES_FETCH_FAILED', ex, file=sys.stderr)
        mv = None
    head = [f"📊 SPX اليوم — {session.isoformat()}"]
    if mv:
        c = gap_call(spx, m, mv[0])
        l1, l2 = c['levels']
        body = [f"الاتجاه: {c['label']} — الثقة {c['conf']}%",
                f"القمة: سيصل على الأقل إلى {l1['high']:,.0f} ({l1['p_high']}%)، ومحتمل {l2['high']:,.0f} ({l2['p_high']}%)",
                f"القاع: سينزل على الأقل إلى {l1['low']:,.0f} ({l1['p_low']}%)، ومحتمل {l2['low']:,.0f} ({l2['p_low']}%)",
                f"الافتتاح المتوقع: {c['anchor']:,.0f} (العقود الآجلة {100*mv[0]:+.2f}% منذ إغلاق أمس، "
                f"آخر قراءة {mv[1].astimezone(RIYADH).strftime('%H:%M')} الرياض)",
                f"أقصى مدى مرجّح: {c['range'][0]:,.0f} – {c['range'][1]:,.0f} ({RANGE_RATE}%)"]
    else:
        lv = call_levels(spx, m)
        c = {'method': 'base', 'anchor': spx, 'direction': 'up', 'conf': UP_RATE,
             'levels': [{'k': None, 'high': lv['high'], 'low': lv['low'], 'p_high': HIT_HIGH, 'p_low': HIT_LOW}],
             'range': [lv['min_low'], lv['max_high']]}
        body = [f"الاتجاه: صاعد 📈 (يصيب {UP_RATE}% من الأيام) — العقود الآجلة غير متاحة الآن",
                f"القمة: سيصل على الأقل إلى {lv['high']:,.0f} ({HIT_HIGH}%)",
                f"القاع: سينزل على الأقل إلى {lv['low']:,.0f} ({HIT_LOW}%)",
                f"أقصى مدى مرجّح: {lv['min_low']:,.0f} – {lv['max_high']:,.0f} ({RANGE_RATE}%)"]
    c.update(session=session.isoformat(), prev_close=spx, m=m, vix=vix, sent_utc=now.isoformat())
    c.pop('label', None)
    print('CALL_JSON ' + json.dumps(c, ensure_ascii=False))
    lines = head + body + [
        "",
        f"إغلاق أمس {spx:,.2f} | VIX {vix:.1f} | الافتتاح {opening.astimezone(RIYADH).strftime('%H:%M')} الرياض"
        + (" ⚠️ وصل بعد الافتتاح" if late else ""),
        *calendar_notes(session),
        "نسب تاريخية، ليست ضمانًا ولا توصية.",
    ]
    return "\n".join(lines)


def send(text):
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        print('NO_TELEGRAM_CREDENTIALS; message not sent')
        return False
    data = urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode()
    resp = json.loads(urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data=data, timeout=20).read())
    print('TELEGRAM_OK' if resp.get('ok') else f'TELEGRAM_FAILED {resp}')
    return bool(resp.get('ok'))


if __name__ == '__main__':
    force = '--force' in sys.argv
    try:
        msg = build(force=force)
    except DataUnavailable as e:
        print('DATA_UNAVAILABLE', e)   # not cached as sent: the next run retries; no failed-run email
        sys.exit(0)
    if msg is None:
        print('NO_SESSION_TODAY')
        sys.exit(0)
    if msg == 'LATE':
        print('LATE_AFTER_OPEN_NOT_SENT')
        sys.exit(0)
    print(msg)
    if '--dry-run' not in sys.argv and not send(msg):
        sys.exit(1)
