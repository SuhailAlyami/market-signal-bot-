"""SPX update after the first hour (10:30 New York): where the day's high and low will likely end up, and the risk of a
big move for the rest of the day. Research: research/boom_20261124/first_hour.py (SPX hourly; parameters fitted on
Dec 2023 - Dec 2024, percentages below measured on 461 untouched sessions 2025-01 .. 2026-11-13).
m = prev_close * VIX_prev / 100 / sqrt(252), the same expected-move unit as daily_range.py.
"""
import json
import math
import os
import sys
from datetime import datetime, time as dtime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_range import CAL, NY, RIYADH, DataUnavailable, closes, last_close, send, yahoo_chart  # noqa: E402

EXT_UP = (0.289, 0.594)     # train quantiles q70, q90 of (day high - first-hour high)/m
EXT_DN = (0.294, 0.736)     # train quantiles q70, q90 of (first-hour low - day low)/m
COV_UP = (75, 95)           # test coverage of those levels
COV_DN = (74, 92)
P_BREAK_UP, P_BREAK_DN = 64, 57   # test: P(day high > first-hour high), P(day low < first-hour low)
P_ONE_HOLDS = 76                  # test: at least one first-hour extreme is the day's extreme
R1_CUTS = (0.339, 0.472)          # train terciles of first-hour range / m
BIG_RATES = (14, 21, 29)          # test: P(|close - 10:30 price| >= 0.5 m) for small / mid / wide first hour
BIG_K = 0.5


def first_hour_bars(session):
    """5-minute ^GSPC bars of the first hour (09:30-10:25 starts). Raises DataUnavailable unless all 12 are present."""
    r = yahoo_chart('^GSPC', 'interval=5m&range=1d')
    q = r['indicators']['quote'][0]
    bars = []
    for i, t in enumerate(r['timestamp']):
        x = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
        if x.date() == session and dtime(9, 30) <= x.time() < dtime(10, 30) and None not in (q['high'][i], q['low'][i], q['close'][i]):
            bars.append((x, q['high'][i], q['low'][i], q['close'][i]))
    if len(bars) < 12:
        raise DataUnavailable(f'first hour incomplete: {len(bars)}/12 five-minute bars')
    return bars


def levels(h1, l1, last, m):
    r1 = (h1-l1)/m
    tier = 0 if r1 < R1_CUTS[0] else (1 if r1 < R1_CUTS[1] else 2)
    return {'h1': h1, 'l1': l1, 'last': last, 'm': m, 'r1': r1,
            'up': [h1+k*m for k in EXT_UP], 'dn': [l1-k*m for k in EXT_DN],
            'big_tier': tier, 'big_rate': BIG_RATES[tier], 'big_pts': BIG_K*m}


def message(session, lv, bar_time):
    tier = ('منخفض', 'عادي', 'مرتفع ⚡')[lv['big_tier']]
    return "\n".join([
        f"⏱️ SPX بعد الساعة الأولى — {session.isoformat()}",
        f"الساعة الأولى: أعلى {lv['h1']:,.0f} | أدنى {lv['l1']:,.0f} | الآن {lv['last']:,.0f}",
        f"🔺 القمة: تتجاوز {lv['h1']:,.0f} ← {P_BREAK_UP}% | الحد المرجّح {lv['up'][0]:,.0f} ({COV_UP[0]}%) | الأقصى {lv['up'][1]:,.0f} ({COV_UP[1]}%)",
        f"🔻 القاع: يكسر {lv['l1']:,.0f} ← {P_BREAK_DN}% | الحد المرجّح {lv['dn'][0]:,.0f} ({COV_DN[0]}%) | الأقصى {lv['dn'][1]:,.0f} ({COV_DN[1]}%)",
        f"أحد طرفي الساعة الأولى يبقى قمة أو قاع اليوم في {P_ONE_HOLDS}% من الأيام.",
        f"خطر حركة كبيرة بقية اليوم (≥ {lv['big_pts']:.0f} نقطة من الآن): {tier} — {lv['big_rate']}% "
        f"(الساعة الأولى {lv['r1']:.2f} من الحركة المتوقعة)",
        "",
        f"آخر شمعة {bar_time.strftime('%H:%M')} نيويورك = {bar_time.astimezone(RIYADH).strftime('%H:%M')} الرياض | "
        "المصدر Yahoo (قد يتأخر). نسب 2025–2026 خارج عينة التدريب، ليست ضمانًا.",
    ])


def build(now=None):
    now = now or datetime.now(timezone.utc)
    ny = now.astimezone(NY)
    session = ny.date()
    if not CAL.is_session(session.isoformat()):
        return None
    if ny.time() < dtime(10, 32):
        return 'EARLY'
    if ny.time() > dtime(12, 30):
        return 'LATE'
    bars = first_hour_bars(session)
    pc = last_close('^GSPC', session)[1]
    vix = last_close('^VIX', session)[1]
    m = pc*vix/100/math.sqrt(252)
    lv = levels(max(b[1] for b in bars), min(b[2] for b in bars), bars[-1][3], m)
    print('FIRST_HOUR_JSON ' + json.dumps({'session': session.isoformat(), **lv}))
    return message(session, lv, bars[-1][0] + (bars[-1][0] - bars[-2][0]))


def score(fh, high, low, close):
    """Score a stored first-hour forecast against the session's final high/low/close."""
    return {'up70': high <= fh['up'][0], 'up90': high <= fh['up'][1], 'dn70': low >= fh['dn'][0], 'dn90': low >= fh['dn'][1],
            'big': abs(close - fh['last']) >= fh['big_pts'], 'tier': fh['big_tier']}


def record_lines(fh_dir, spx, target):
    """Evening lines: today's first-hour forecast scored, plus the cumulative live record vs the promised rates."""
    import glob
    from promotion import wilson
    if not fh_dir or not os.path.isdir(fh_dir):
        return []
    load = lambda d: json.loads(open(os.path.join(fh_dir, f'{d}.json')).read())
    days = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(fh_dir, '*.json')))
    hist = [score(load(d), spx[d][1], spx[d][2], spx[d][3]) for d in days if d in spx and d <= target]
    if not hist:
        return []
    ok = lambda b: '✅' if b else '❌'
    out = []
    if target in days and target in spx:
        t = score(load(target), spx[target][1], spx[target][2], spx[target][3])
        out.append(f"⏱️ تنبؤ الساعة الأولى: القمة المرجّحة {ok(t['up70'])} الأقصى {ok(t['up90'])} | "
                   f"القاع المرجّح {ok(t['dn70'])} الأقصى {ok(t['dn90'])} | حركة كبيرة بعدها: {'حدثت' if t['big'] else 'لم تحدث'}")
    n = len(hist)
    parts = []
    for key, claim, name in (('up70', COV_UP[0], 'القمة المرجّحة'), ('up90', COV_UP[1], 'القمة القصوى'),
                             ('dn70', COV_DN[0], 'القاع المرجّح'), ('dn90', COV_DN[1], 'القاع الأقصى')):
        k = sum(h[key] for h in hist)
        lo, hi = wilson(k, n)
        flag = '' if n < 20 or lo*100 <= claim <= hi*100 else ' ⚠️'
        parts.append(f"{name} {k}/{n} ({claim}%){flag}")
    out.append(f"📒 سجل الساعة الأولى ({n} جلسة): " + ' | '.join(parts))
    return out


if __name__ == '__main__':
    try:
        msg = build()
    except DataUnavailable as e:
        print('DATA_UNAVAILABLE', e)   # not marked sent: the next slot retries
        sys.exit(0)
    if msg in (None, 'EARLY', 'LATE'):
        print({None: 'NO_SESSION_TODAY', 'EARLY': 'TOO_EARLY', 'LATE': 'LATE_NOT_SENT'}[msg])
        sys.exit(0)
    print(msg)
    send(msg)
