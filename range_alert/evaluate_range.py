"""Post-close check of the pre-open SPX range alert (Telegram). Stateless: bands are recomputed from the
prior close and prior VIX close (same formula as daily_range.py), so no storage is needed.
Cumulative live record counts every completed session from LIVE_START."""
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xc

from daily_range import HIT_HIGH, HIT_LOW, RANGE_RATE, UP_RATE, call_levels, send

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
            'broke_up1': h > pc+m, 'broke_dn1': l < pc-m,
            'hit_high': h >= call_levels(pc, m)['high'], 'hit_low': l <= call_levels(pc, m)['low'],
            'call_high': call_levels(pc, m)['high'], 'call_low': call_levels(pc, m)['low']}


POS = {'Buy': 1, 'Overweight': 1, 'Sell': -1, 'Underweight': -1}   # Hold / REVIEW = no position


def shadow_lines(records_dir, spy, day):
    """Score TradingAgents shadow decisions against SPY close-to-close returns (decision made before the open
    with data up to the previous close). Baseline: always long. Returns Arabic lines ([] if no records)."""
    if not records_dir or not os.path.isdir(records_dir):
        return []
    days = sorted(spy)
    rows = []
    for f in sorted(os.listdir(records_dir)):
        if not f.endswith('.json'):
            continue
        r = json.loads(open(os.path.join(records_dir, f)).read())
        d = r.get('session')
        if not d or d > day or d not in spy or days.index(d) == 0:
            continue
        prev = days[days.index(d)-1]
        ret = 100*(spy[d][3]/spy[prev][3]-1)
        rows.append({'d': d, 'sig': r.get('signal'), 'pos': POS.get(r.get('signal'), 0), 'ret': ret})
    if not rows:
        return []
    AR = {'Buy': 'شراء', 'Overweight': 'زيادة', 'Hold': 'احتفاظ', 'Underweight': 'تخفيف', 'Sell': 'بيع'}
    out = ["", "🤖 تقييم TradingAgents (تجريبي):"]
    today = [x for x in rows if x['d'] == day]
    if today:
        x = today[0]
        verdict = 'بلا مركز' if x['pos'] == 0 else ('✅ صحيح' if x['pos']*x['ret'] > 0 else '❌ خطأ')
        out.append(f"اليوم: {AR.get(x['sig'], x['sig'])} | SPY {x['ret']:+.2f}% → {verdict}")
    calls = [x for x in rows if x['pos'] != 0]
    hits = sum(x['pos']*x['ret'] > 0 for x in calls)
    strat, base = sum(x['pos']*x['ret'] for x in rows), sum(x['ret'] for x in rows)
    out.append(f"التراكمي ({len(rows)} جلسة): قرارات اتجاه {len(calls)}، صحيحة {hits} | "
               f"اتباعه {strat:+.2f}% مقابل \"صاعد دائمًا\" {base:+.2f}%")
    return out


def build(now=None, force=False):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date().isoformat()
    sessions = [str(s.date()) for s in CAL.sessions_in_range('2026-01-02', today)]
    done = [d for d in sessions if CAL.session_close(d).to_pydatetime() + timedelta(minutes=15) <= now]
    if not done:
        return None
    # Always the latest closed session; delivery is deduplicated per evaluated session by the workflow cache,
    # so a late or next-morning run still delivers a result that was missed, exactly once.
    spx, vix = daily('^GSPC'), daily('^VIX')
    target = done[-1]
    if target not in spx:
        raise RuntimeError(f'Yahoo has no daily bar for {target} yet')
    e = evaluate(spx, vix, target)
    live = [evaluate(spx, vix, d) for d in done if d >= LIVE_START and d in spx]
    n = len(live)
    ok = lambda b: '✅' if b else '❌'
    lines = [
        f"📈 نتيجة SPX — {target}",
        f"الأعلى {e['high']:,.0f} | الأدنى {e['low']:,.0f} | الإغلاق {e['close']:,.0f}",
        f"الاتجاه صاعد: {ok(e['up'])} ({'صعد' if e['up'] else 'نزل'} {e['close']-e['prev_close']:+,.0f})",
        f"القمة ≥ {e['call_high']:,.0f}: {ok(e['hit_high'])}",
        f"القاع ≤ {e['call_low']:,.0f}: {ok(e['hit_low'])}",
        f"داخل المدى {e['prev_close']-e['move']:,.0f} – {e['prev_close']+e['move']:,.0f}: {ok(e['in1'])}",
    ]
    if n:
        pct = lambda k: f"{sum(x[k] for x in live)}/{n}"
        lines += ["", f"السجل منذ {LIVE_START} ({n} جلسة):",
                  f"الاتجاه {pct('up')} (المتوقع {UP_RATE}%) | القمة {pct('hit_high')} ({HIT_HIGH}%) | "
                  f"القاع {pct('hit_low')} ({HIT_LOW}%) | المدى {pct('in1')} ({RANGE_RATE}%)"]
    try:
        lines += shadow_lines(os.environ.get('SHADOW_RECORDS'), daily('SPY'), target)
    except Exception as ex:  # noqa: BLE001  (scoring must never block the range evaluation)
        print('SHADOW_SCORING_FAILED', ex, file=sys.stderr)
    lines.append("المصدر: Yahoo يومي (متأخر).")
    return "\n".join(lines)


def last_closed(now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date().isoformat()
    done = [str(s.date()) for s in CAL.sessions_in_range('2026-01-02', today)
            if CAL.session_close(s).to_pydatetime() + timedelta(minutes=15) <= now]
    return done[-1] if done else 'none'


if __name__ == '__main__':
    if '--print-target' in sys.argv:
        print(last_closed()); sys.exit(0)
    if '--force' not in sys.argv and last_closed() < '2026-11-17':
        # 2026-11-16 was delivered by a forced manual run before per-session dedupe existed.
        print('ALREADY_DELIVERED'); sys.exit(0)
    msg = build(force='--force' in sys.argv)
    if msg is None:
        print('SESSION_NOT_CLOSED_OR_NO_SESSION')
        sys.exit(0)
    print(msg)
    if '--dry-run' not in sys.argv and not send(msg):
        sys.exit(1)
