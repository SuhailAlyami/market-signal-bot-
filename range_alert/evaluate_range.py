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

from daily_range import HIT_HIGH, HIT_LOW, RANGE_RATE, STRONG, UP_RATE, DataUnavailable, call_levels, send, yahoo_chart

NY = ZoneInfo('America/New_York')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')
LIVE_START = '2026-11-16'  # first session announced by the pre-open alert


def daily(symbol):
    r = yahoo_chart(symbol, 'interval=1d&range=1y')
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


K_BOOM = 0.75   # strong move: |close - open| >= 0.75 m (same definition as the explosion model)
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


def load_call(calls_dir, day):
    f = os.path.join(calls_dir or '', f'{day}.json')
    return json.loads(open(f).read()) if calls_dir and os.path.isfile(f) else None


def score_call(c, o, h, l, close):
    """Score a stored morning call against the session's actual high/low/close."""
    pc = c['prev_close']
    d = c['direction']
    dir_ok = None if d == 'flat' else ((close > pc) if d == 'up' else (close < pc))
    lv = [{'high': x['high'], 'low': x['low'], 'hit_high': h >= x['high'], 'hit_low': l <= x['low'],
           'p_high': x['p_high'], 'p_low': x['p_low']} for x in c['levels']]
    return {'dir': d, 'conf': c['conf'], 'dir_ok': dir_ok, 'levels': lv, 'method': c.get('method'),
            'in_range': c['range'][0] <= l and h <= c['range'][1]}


def score_trade(c, o, close):
    """P&L in SPX points of the conditional open-to-close trade, before costs; None when no trade was triggered."""
    t = c.get('trade')
    if not t:
        return None
    if o >= t['long_above']:
        return close - o
    if o <= t['short_below']:
        return o - close
    return None


def call_lines(calls_dir, spx, target):
    c = load_call(calls_dir, target)
    if not c or target not in spx:
        return None
    o, h, l, close = spx[target]
    s = score_call(c, o, h, l, close)
    ok = lambda b: '✅' if b else '❌'
    AR = {'up': 'صاعد', 'down': 'هابط', 'flat': 'محايد'}
    pc = c['prev_close']
    lines = [f"📈 نتيجة SPX — {target}",
             f"الأعلى {h:,.0f} | الأدنى {l:,.0f} | الإغلاق {close:,.0f} ({close-pc:+,.0f} عن أمس)",
             f"الاتجاه {AR[s['dir']]} ({s['conf']}%): " + ('— بلا حكم' if s['dir_ok'] is None else ok(s['dir_ok']))]
    for x in s['levels']:
        lines.append(f"القمة ≥ {x['high']:,.0f} ({x['p_high']}%): {ok(x['hit_high'])} | "
                     f"القاع ≤ {x['low']:,.0f} ({x['p_low']}%): {ok(x['hit_low'])}")
    lines.append(f"داخل المدى {c['range'][0]:,.0f} – {c['range'][1]:,.0f}: {ok(s['in_range'])}")
    if c.get('trade'):
        pnl = score_trade(c, o, close)
        lines.append(f"🎯 الصفقة المشروطة: افتتاح {o:,.0f} — " +
                     ("لم تتفعّل (بين المستويين)" if pnl is None else f"{'شراء' if o >= c['trade']['long_above'] else 'بيع'} ← {pnl:+,.1f} نقطة {ok(pnl > 1)}"))
    if c.get('explosion'):
        ex = c['explosion']
        lines.append(f"حركة قوية (≥ {ex['threshold_pts']:.0f} نقطة من الافتتاح): {'حدثت' if abs(close-o) >= ex['threshold_pts'] else 'لم تحدث'}"
                     f" — الخطر الصباحي: {ex['label']}")
    if c.get('gamma'):
        boom = abs(close-o) >= K_BOOM*c['m']
        lines.append(f"رادار الغاما: {'سالب' if c['gamma']['regime'] == 'negative' else 'موجب'} — حركة قوية: {'حدثت' if boom else 'لم تحدث'}")
    hist = [score_call(load_call(calls_dir, d), *spx[d]) for d in sorted(spx) if d <= target and load_call(calls_dir, d)]
    dirs = [x['dir_ok'] for x in hist if x['dir_ok'] is not None]
    strong = [x['dir_ok'] for x in hist if x['dir_ok'] is not None and x['conf'] >= STRONG]
    first = [x['levels'][0] for x in hist]
    exr = []
    for d in sorted(spx):
        cd = load_call(calls_dir, d) if d <= target else None
        if cd and cd.get('explosion'):
            exr.append((cd['explosion']['tier'] != 'normal', abs(spx[d][3]-spx[d][0]) >= cd['explosion']['threshold_pts']))
    gam = []
    for d in sorted(spx):
        cd = load_call(calls_dir, d) if d <= target else None
        if cd and cd.get('gamma') and cd.get('m'):
            gam.append((cd['gamma']['regime'] == 'negative', abs(spx[d][3]-spx[d][0]) >= K_BOOM*cd['m']))
    ex_line = ""
    pnls = [p for d in sorted(spx) if d <= target and load_call(calls_dir, d)
            for p in [score_trade(load_call(calls_dir, d), spx[d][0], spx[d][3])] if p is not None]
    if pnls:
        ex_line += f" | الصفقات {sum(p > 1 for p in pnls)}/{len(pnls)} رابحة، المجموع {sum(pnls) - len(pnls):+,.0f} نقطة بعد التكلفة"
    if exr:
        hi = [b for a, b in exr if a]; lo = [b for a, b in exr if not a]
        ex_line = f" | الحركة القوية: أيام الخطر {sum(hi)}/{len(hi)}، الأيام العادية {sum(lo)}/{len(lo)}"
    if gam:
        neg = [b for a, b in gam if a]; pos = [b for a, b in gam if not a]
        ex_line += f" | الغاما السالبة: انفجار {sum(neg)}/{len(neg)}، الموجبة {sum(pos)}/{len(pos)}"
    lines += ["", f"السجل ({len(hist)} جلسة): الاتجاه {sum(dirs)}/{len(dirs)} (القوي منه {sum(strong)}/{len(strong)}) | "
              f"القمة الأولى {sum(x['hit_high'] for x in first)}/{len(first)} | القاع الأول {sum(x['hit_low'] for x in first)}/{len(first)}" + ex_line]
    return lines


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
        raise DataUnavailable(f'Yahoo has no daily bar for {target} yet')
    e = evaluate(spx, vix, target)
    live = [evaluate(spx, vix, d) for d in done if d >= LIVE_START and d in spx]
    n = len(live)
    stored = call_lines(os.environ.get('CALLS_DIR'), spx, target)
    ok = lambda b: '✅' if b else '❌'
    lines = stored or [
        f"📈 نتيجة SPX — {target}",
        f"الأعلى {e['high']:,.0f} | الأدنى {e['low']:,.0f} | الإغلاق {e['close']:,.0f}",
        f"الاتجاه صاعد: {ok(e['up'])} ({'صعد' if e['up'] else 'نزل'} {e['close']-e['prev_close']:+,.0f})",
        f"القمة ≥ {e['call_high']:,.0f}: {ok(e['hit_high'])}",
        f"القاع ≤ {e['call_low']:,.0f}: {ok(e['hit_low'])}",
        f"داخل المدى {e['prev_close']-e['move']:,.0f} – {e['prev_close']+e['move']:,.0f}: {ok(e['in1'])}",
    ]
    if n and not stored:
        pct = lambda k: f"{sum(x[k] for x in live)}/{n}"
        lines += ["", f"السجل منذ {LIVE_START} ({n} جلسة):",
                  f"الاتجاه {pct('up')} (المتوقع {UP_RATE}%) | القمة {pct('hit_high')} ({HIT_HIGH}%) | "
                  f"القاع {pct('hit_low')} ({HIT_LOW}%) | المدى {pct('in1')} ({RANGE_RATE}%)"]
    if os.environ.get('SHADOW_RECORDS'):   # TradingAgents shadow stopped 2026-11-18; kept for manual runs
        try:
            lines += shadow_lines(os.environ['SHADOW_RECORDS'], daily('SPY'), target)
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
    try:
        msg = build(force='--force' in sys.argv)
    except DataUnavailable as e:
        print('DATA_UNAVAILABLE', e)   # not cached as delivered: the next run retries; no failed-run email
        sys.exit(0)
    if msg is None:
        print('SESSION_NOT_CLOSED_OR_NO_SESSION')
        sys.exit(0)
    print(msg)
    if '--dry-run' not in sys.argv:
        send(msg)   # TELEGRAM_OK is what the workflow records as delivered; otherwise a later run retries
