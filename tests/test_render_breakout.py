import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import render_breakout as R


def day_bars(day=(2026, 11, 24), break_at=40, vol=3.0):
    start = datetime(*day, 9, 30, tzinfo=R.NY).astimezone(timezone.utc)
    B = []
    for k in range(78):
        t = start + timedelta(minutes=5*k)
        o, h, l, c, v = 700, 700.2, 699.8, 700, 1000
        if k == break_at:
            h, c, v = 700.5, 700.45, 1000*vol
        if k > break_at:
            o = c = 700.6+0.1*(k-break_at); h, l = c+0.2, c-0.05
        B.append((t, o, h, l, c, v))
    return B


class BreakoutTests(unittest.TestCase):
    def test_volume_surge_break_wins_and_weak_volume_is_ignored(self):
        tr = R.trades(day_bars())
        self.assertEqual((len(tr), tr[0]['d'], tr[0]['R']), (1, 1, 1.5))
        self.assertEqual(R.trades(day_bars(vol=1.2)), [])

    def test_sent_once_capped_per_day_and_no_old_signals_after_restart(self):
        B = day_bars()
        entry_end = B[40][0] + timedelta(minutes=5)
        sent = []
        with tempfile.TemporaryDirectory() as d:
            st = R.State(os.path.join(d, 's.json'))
            for m in range(0, 30):
                R.check(entry_end + timedelta(minutes=m), st, lambda t: sent.append(t) or True, fetch=lambda now: B)
            self.assertEqual(len(sent), 1)
            st2 = R.State(os.path.join(d, 's.json'))            # restart: state reloaded, nothing resent
            R.check(entry_end + timedelta(minutes=3), st2, lambda t: sent.append(t) or True, fetch=lambda now: B)
            self.assertEqual(len(sent), 1)
        self.assertIn('شراء', sent[0]); self.assertIn('وقف', sent[0]); self.assertIn('هدف', sent[0])

    def test_holiday_and_outside_hours_do_nothing(self):
        boom = lambda now: (_ for _ in ()).throw(AssertionError('must not fetch'))
        st = R.State('/nonexistent/x.json')
        self.assertEqual(R.check(datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc), st, print, fetch=boom), 0)
        self.assertEqual(R.check(datetime(2026, 11, 24, 13, 0, tzinfo=timezone.utc), st, print, fetch=boom), 0)

    def test_session_loop_sends_live_signal_once_and_stops_after_last_entry(self):
        B = day_bars()
        t = [datetime(2026, 11, 24, 11, 0, tzinfo=R.NY).astimezone(timezone.utc)]
        def now_fn(): return t[0]
        def sleep(s): t[0] += timedelta(seconds=s)
        def fetch(now): return [b for b in B if b[0] + timedelta(minutes=5) <= now]
        sent = []
        with tempfile.TemporaryDirectory() as d:
            os.environ['HUNTER_STATE_DIR'] = d
            n = R.run_session(send=lambda m: sent.append(m) or True, now_fn=now_fn, sleep=sleep, fetch=fetch)
        self.assertEqual((n, len(sent)), (1, 1))
        self.assertGreaterEqual(t[0].astimezone(R.NY).hour*60 + t[0].astimezone(R.NY).minute, 15*60+40)

    def test_session_loop_exits_on_holiday_and_outside_start_window(self):
        boom = lambda now: (_ for _ in ()).throw(AssertionError('must not fetch'))
        hol = lambda: datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
        early = lambda: datetime(2026, 11, 24, 14, 55, tzinfo=timezone.utc)   # 09:55 NY (winter slot in summer time)
        self.assertEqual(R.run_session(send=print, now_fn=hol, sleep=None, fetch=boom), 0)
        self.assertEqual(R.run_session(send=print, now_fn=early, sleep=None, fetch=boom), 0)


if __name__ == '__main__':
    unittest.main()
