"""Live breakout detector inside the Render process (market_signal_bot.py), sent over the existing Telegram bot.

Rule (research/filters_20261124/squeeze.py, the only filter with a positive edge in both train and test):
SPY 5m, box = high/low of the 6 bars ending at bar i (i >= 21 bars into the session, 10:00-15:00 NY). Entry = stop
order 1 tick beyond the box on the first break within 6 bars whose volume >= 1.5 x the prior 20-bar average;
stop = other side of the box; target = 1.5 x risk; exit after 12 bars or at the close.
Research: train +0.07 R, test +0.10 R (54% wins, n=39, CI includes 0). Not proven; at most MAX_PER_DAY alerts a day.
Stdlib only (no new dependency on Render). Data and Telegram failures are logged, never sent as messages.
"""
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LOG = logging.getLogger('render_breakout')
NY, RIYADH = ZoneInfo('America/New_York'), ZoneInfo('Asia/Riyadh')
N, K, H, T, VOL, TICK = 6, 6, 12, 1.5, 1.5, 0.01
MAX_PER_DAY = int(os.getenv('BREAKOUT_MAX_PER_DAY', '3'))
# NYSE (nyse.com, checked 2026-11-24); extend yearly.
HOLIDAYS = {'2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07',
            '2026-11-26', '2026-12-25', '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18',
            '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24'}
EARLY_CLOSE = {'2026-11-27', '2026-12-24', '2027-11-26'}


def is_session(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def close_mins(d):
    return 13*60 if d.isoformat() in EARLY_CLOSE else 16*60


def fetch_spy_5m(now, rng='1d'):
    """Completed SPY 5m bars of regular sessions: [(t_utc, o, h, l, c, v)]."""
    last = None
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        try:
            req = urllib.request.Request(f'https://{host}/v8/finance/chart/SPY?interval=5m&range={rng}',
                                         headers={'User-Agent': 'Mozilla/5.0 (suhail-hunter render)'})
            r = json.loads(urllib.request.urlopen(req, timeout=15).read())['chart']['result'][0]
            q = r['indicators']['quote'][0]
            out = []
            for i, ts in enumerate(r['timestamp']):
                v = [q['open'][i], q['high'][i], q['low'][i], q['close'][i]]
                if None in v:
                    continue
                t = datetime.fromtimestamp(ts, timezone.utc)
                x = t.astimezone(NY)
                m = x.hour*60+x.minute
                if t + timedelta(minutes=5) <= now and 570 <= m < close_mins(x.date()):
                    out.append((t, *v, q['volume'][i] or 0))
            return out
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f'Yahoo SPY unavailable: {last}')


def _atr20(B, i):
    return sum(max(B[j][2]-B[j][3], abs(B[j][2]-B[j-1][4]), abs(B[j][3]-B[j-1][4])) for j in range(i-19, i+1))/20


def trades(B):
    """One session of completed 5m bars. Same loop as squeeze.py events(vol_conf=True, cut=None)."""
    out, i = [], 21
    while i < len(B)-1:
        x = B[i][0].astimezone(NY)
        if not (600 <= x.hour*60+x.minute <= 900) or not _atr20(B, i) > 0:
            i += 1
            continue
        box = B[i-N+1:i+1]
        hi, lo = max(b[2] for b in box), min(b[3] for b in box)
        done = False
        for j in range(i+1, min(i+1+K, len(B))):
            up, dn = B[j][2] > hi, B[j][3] < lo
            if up and dn:
                break
            if not (up or dn):
                continue
            avg = sum(b[5] for b in B[j-20:j])/20
            if not avg or B[j][5] < VOL*avg:
                break
            d = 1 if up else -1
            e = hi+TICK if up else lo-TICK
            risk = e-lo+TICK if up else hi+TICK-e
            stop, tgt = e-d*risk, e+d*T*risk
            R, k = None, j
            if (B[j][3] <= stop) if d > 0 else (B[j][2] >= stop):
                R = -1.0
            elif (B[j][2] >= tgt) if d > 0 else (B[j][3] <= tgt):
                R = T
            while R is None:
                k += 1
                if k >= len(B) or k > j+H:
                    R = d*(B[k-1][4]-e)/risk
                    break
                hs = B[k][3] <= stop if d > 0 else B[k][2] >= stop
                ht = B[k][2] >= tgt if d > 0 else B[k][3] <= tgt
                R = -1.0 if hs else (T if ht else None)
            out.append(dict(entry_t=B[j][0], d=d, e=e, stop=stop, tgt=tgt, R=R, vol_x=B[j][5]/avg))
            i, done = k, True
            break
        if not done:
            i += 1
    return out


def message(x):
    rt = lambda t: t.astimezone(RIYADH).strftime('%H:%M')
    return '\n'.join([
        f"🎯 كسر صندوق مع حجم — {'شراء 📈' if x['d'] > 0 else 'بيع 📉'} (كاشف تحت الاختبار)",
        f"SPY: دخول {x['e']:.2f} | وقف {x['stop']:.2f} | هدف {x['tgt']:.2f} (1.5 × المخاطرة)",
        f"≈ SPX: دخول {x['e']*10:,.0f} | وقف {x['stop']*10:,.0f} | هدف {x['tgt']*10:,.0f}",
        f"الحجم {x['vol_x']:.1f}× المتوسط | شمعة {rt(x['entry_t'])}–{rt(x['entry_t']+timedelta(minutes=5))} الرياض | خروج بعد ساعة كحد أقصى",
        "البحث: +0.10R على بيانات جديدة (54% ربح)، غير مثبت إحصائيًا. حجم صغير.",
    ])


class State:
    """Sent entries per day, persisted to a small JSON file (best effort: Render free may erase it on redeploy)."""
    def __init__(self, path):
        self.path = path
        try:
            self.data = json.loads(open(path).read())
        except (OSError, ValueError):
            self.data = {}

    def sent(self, day):
        return self.data.get(day, [])

    def add(self, day, key):
        self.data = {d: v for d, v in self.data.items() if d >= (date.fromisoformat(day)-timedelta(days=7)).isoformat()}
        self.data.setdefault(day, []).append(key)
        try:
            os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
            tmp = self.path + '.tmp'
            open(tmp, 'w').write(json.dumps(self.data))
            os.replace(tmp, self.path)
        except OSError as e:
            LOG.warning('breakout state not saved: %s', e)


def check(now, state, send, fetch=fetch_spy_5m):
    """One pass. Sends new entries whose bar completed in the last 10 minutes, at most MAX_PER_DAY a day."""
    x = now.astimezone(NY)
    d = x.date()
    if not is_session(d) or not (600 <= x.hour*60+x.minute <= close_mins(d)+5):
        return 0
    B = [b for b in fetch(now) if b[0].astimezone(NY).date() == d]
    n = 0
    for tr in trades(B):
        key = tr['entry_t'].isoformat()
        age = now - (tr['entry_t']+timedelta(minutes=5))
        if key in state.sent(d.isoformat()) or not (timedelta(0) <= age <= timedelta(minutes=10)):
            continue
        if len(state.sent(d.isoformat())) >= MAX_PER_DAY:
            break
        if send(message(tr)):
            state.add(d.isoformat(), key)
            n += 1
    return n


def telegram_sender(token, chat_id):
    def send(text):
        try:
            body = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode()
            with urllib.request.urlopen(urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=body), timeout=10) as r:
                return r.status == 200
        except Exception as e:  # noqa: BLE001
            LOG.warning('breakout Telegram send failed: %s', type(e).__name__)
            return False
    return send


def start(token=None, chat_id=None):
    token = token or os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id or os.getenv('BREAKOUT_ALERTS', 'true').lower() != 'true':
        LOG.info('breakout alerts off (no Telegram credentials or BREAKOUT_ALERTS=false)')
        return None
    state = State(os.path.join(os.getenv('HUNTER_STATE_DIR', '.hunter-state'), 'breakout_sent.json'))
    send = telegram_sender(token, chat_id)

    def loop():
        while True:
            try:
                check(datetime.now(timezone.utc), state, send)
            except Exception as e:  # noqa: BLE001  (data problems are logged only)
                LOG.warning('breakout check failed: %s', e)
            time.sleep(60)
    th = threading.Thread(target=loop, daemon=True, name='breakout-alerts')
    th.start()
    LOG.info('breakout alerts ON (max %d a day)', MAX_PER_DAY)
    return th


def run_session(send=None, now_fn=lambda: datetime.now(timezone.utc), sleep=time.sleep, fetch=fetch_spy_5m):
    """One live session loop (GitHub Actions job): checks every 60 s from start until the last possible entry
    (15:35 NY, or 5 min after an early close). Exits at once on holidays or when started too early/late."""
    if send is None:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'range_alert'))
        from daily_range import send as tg_send   # Telegram with retries (same channel as the daily messages)
        send = tg_send
    x = now_fn().astimezone(NY)
    d = x.date()
    end = min(15*60+40, close_mins(d)+5)
    if not is_session(d):
        print('NO_SESSION_TODAY'); return 0
    if not (10*60+45 <= x.hour*60+x.minute <= 12*60+30):
        print('OUTSIDE_START_WINDOW', x.strftime('%H:%M')); return 0
    state, n = State(os.path.join(os.getenv('HUNTER_STATE_DIR', '.hunter-state'), 'breakout_sent.json')), 0
    print('BREAKOUT_LIVE_START', x.isoformat())
    while True:
        now = now_fn()
        m = now.astimezone(NY)
        if m.hour*60+m.minute > end:
            break
        try:
            n += check(now, state, send, fetch)
        except Exception as e:  # noqa: BLE001  (data problems are logged only, never sent)
            print('CHECK_FAILED', e)
        sleep(60)
    print('BREAKOUT_LIVE_END sent', n)
    return n


if __name__ == '__main__':
    run_session()
