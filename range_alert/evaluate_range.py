"""Post-close check of the pre-open SPX range alert (Telegram). Stateless: bands are recomputed from the
prior close and prior VIX close (same formula as daily_range.py), so no storage is needed.
Cumulative live record counts every completed session from LIVE_START."""
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xc

from daily_range import send

NY = ZoneInfo('America/New_York')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')
LIVE_START = '2026-11-16'  # first session announced by the pre-open alert


def daily(symbol):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?interval=1d&range=1y'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-range-alert)'})
    r = json.loads(urllib.request.urlopen(req, timeout=20).read())['chart']['result'][0]
    q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date().isoformat(): (q['open'][i], q['high'][i], q['low'][i], q['close'][i])
            for i, t in enumerate(r['timestamp']) if q['close'][i] and q['high'][i] and q['low'][i]}


def evaluate(spx, vix, day):
    days = sorted(d for d in spx if d in vix)
    i = days.index(day)
    prev = days[i-1]
    pc, v = spx[prev][3], vix[prev][3]
    m = pc*v/100/math.sqrt(252)
    o, h, l, c = spx[day]
    inside = lambda k: l >= pc-k*m and h <= pc+k*m
    return {'day': day, 'prev_close': pc, 'move': m, 'high': h, 'low': l, 'close': c,
            'in1': inside(1.0), 'in15': inside(1.5), 'up': c > pc,
            'broke_up1': h > pc+m, 'broke_dn1': l < pc-m}


def build(now=None, force=False):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date().isoformat()
    sessions = [str(s.date()) for s in CAL.sessions_in_range('2026-01-02', today)]
    done = [d for d in sessions if CAL.session_close(d).to_pydatetime() + timedelta(minutes=15) <= now]
    if not done or (done[-1] != today and not force):
        return None  # today's session not closed yet (or not a session)
    spx, vix = daily('^GSPC'), daily('^VIX')
    target = done[-1]
    if target not in spx:
        raise RuntimeError(f'Yahoo has no daily bar for {target} yet')
    e = evaluate(spx, vix, target)
    live = [evaluate(spx, vix, d) for d in done if d >= LIVE_START and d in spx]
    n = len(live)
    sides = []
    if e['broke_up1']:
        sides.append('تجاوز الحد الأعلى')
    if e['broke_dn1']:
        sides.append('كسر الحد الأدنى')
    yes = lambda b: '✅ داخل' if b else '❌ خارج'
    lines = [
        f"📈 نتيجة جلسة {target}",
        f"الأعلى: {e['high']:,.2f} | الأدنى: {e['low']:,.2f} | الإغلاق: {e['close']:,.2f} ({'صاعد' if e['up'] else 'هابط'})",
        f"النطاق المرجّح {e['prev_close']-e['move']:,.0f} – {e['prev_close']+e['move']:,.0f}: {yes(e['in1'])}" + (f" ({'، '.join(sides)})" if sides else ""),
        f"النطاق الواسع {e['prev_close']-1.5*e['move']:,.0f} – {e['prev_close']+1.5*e['move']:,.0f}: {yes(e['in15'])}",
        "",
    ]
    if n:
        lines += [f"السجل الحي منذ {LIVE_START} ({n} جلسة):",
                  f"المرجّح: {sum(x['in1'] for x in live)}/{n} = {100*sum(x['in1'] for x in live)/n:.0f}% (المتوقع 68.7%)",
                  f"الواسع: {sum(x['in15'] for x in live)}/{n} = {100*sum(x['in15'] for x in live)/n:.0f}% (المتوقع 90.1%)"]
    else:
        lines.append(f"السجل الحي يبدأ من جلسة {LIVE_START}.")
    lines.append("المصدر: Yahoo يومي (متأخر).")
    return "\n".join(lines)


if __name__ == '__main__':
    msg = build(force='--force' in sys.argv)
    if msg is None:
        print('SESSION_NOT_CLOSED_OR_NO_SESSION')
        sys.exit(0)
    print(msg)
    if '--dry-run' not in sys.argv and not send(msg):
        sys.exit(1)
