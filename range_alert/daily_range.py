"""Pre-open SPX daily range alert (Telegram). Expected 1-day move = prior close x (VIX/100) / sqrt(252).
Historical coverage 2010-2026 (both daily high and low inside the band): +/-1 move 68.7%, +/-1.5 moves 90.1%.
No direction forecast: SPX closed up on 54.5% of days since 2010 (base rate, not a signal). Data: Yahoo daily (delayed)."""
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY, RIYADH = ZoneInfo('America/New_York'), ZoneInfo('Asia/Riyadh')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')


def closes(symbol, before, rng='3mo'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?interval=1d&range={rng}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-range-alert)'})
    r = json.loads(urllib.request.urlopen(req, timeout=20).read())['chart']['result'][0]
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
    spx_rows = closes('^GSPC', session)
    (d, spx), (dv, vix) = spx_rows[-1], last_close('^VIX', session)
    rv = realized_vol_21(spx_rows)
    m = spx*vix/100/math.sqrt(252)
    late = now > opening
    lines = [
        f"📊 نطاق SPX المتوقع — جلسة {session.isoformat()}",
        f"إغلاق {d.isoformat()}: {spx:,.2f} | VIX: {vix:.2f}",
        f"الحركة المتوقعة: ±{m:.0f} نقطة",
        "",
        f"النطاق المرجّح (68.7% تاريخيًا): {spx-m:,.0f} – {spx+m:,.0f}",
        f"النطاق الواسع (90.1% تاريخيًا): {spx-1.5*m:,.0f} – {spx+1.5*m:,.0f}",
        "",
        options_cost_line(vix, rv),
        "",
        *move_lines(m),
        "",
        "الاتجاه: لا توقع (منذ 2010 أغلق SPX صاعدًا 54.5% من الأيام).",
        f"الافتتاح: {opening.astimezone(RIYADH).strftime('%H:%M')} بتوقيت الرياض"
        + (" — ⚠️ وصل التنبيه بعد الافتتاح" if late else ""),
        *calendar_notes(session),
        "المصدر: Yahoo يومي (متأخر). نطاق إحصائي، ليس توصية تداول.",
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
    msg = build(force=force)
    if msg is None:
        print('NO_SESSION_TODAY')
        sys.exit(0)
    print(msg)
    if '--dry-run' not in sys.argv and not send(msg):
        sys.exit(1)
