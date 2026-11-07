import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from objective_review import Bar, NY, execute, first_event, load_sessions


class ResearchProtocolTests(unittest.TestCase):
    def bar(self, minute, o=100, h=101, l=99, c=100):
        return Bar(datetime(2026, 11, 6, 10, tzinfo=NY) + timedelta(minutes=minute), o, h, l, c)

    def test_signal_is_causal_and_first_event_is_not_reselected(self):
        bars = [self.bar(0), self.bar(15), self.bar(30, 100, 104, 99, 103)]
        first = first_event(bars, 'breakout_90m')
        self.assertEqual(first['decision'], self.bar(45).at)
        self.assertEqual(first, first_event(bars + [self.bar(45, 100, 200, 1, 10)], 'breakout_90m'))

    def test_reclaim_needs_a_previous_closed_bar_outside(self):
        bars = [self.bar(0), self.bar(15), self.bar(30, 100, 101, 97, 98),
                self.bar(45, 98, 101, 97, 100)]
        self.assertIsNone(first_event(bars[:3], 'reclaim_30m'))
        self.assertEqual(first_event(bars, 'reclaim_30m')['side'], 1)

    def test_latency_uses_later_open(self):
        raw = [self.bar(i, 100+i/100, 101, 99, 100) for i in range(45)]
        event = dict(decision=raw[0].at, side=1, stop=90)
        result = execute(raw, 1, self.bar(60).at, event, 15, 30)
        self.assertEqual(result['entry'], 100.15)
        self.assertEqual(result['entry_Riyadh'], raw[15].at.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Riyadh')).isoformat())

    def test_stop_target_same_bar_reports_both_bounds(self):
        raw = [self.bar(0, 100, 103, 98, 100)]
        result = execute(raw, 1, self.bar(1).at, dict(decision=raw[0].at, side=1, stop=99), 0, 1)
        self.assertEqual((result['gross_low'], result['gross_high']), (-1, 2))
        self.assertEqual(result['exit'], 'ambiguous')

    def test_stop_gap_is_worse_than_stop_price(self):
        raw = [self.bar(0, 100, 100.5, 99.5, 100), self.bar(1, 97, 98, 96, 97)]
        result = execute(raw, 1, self.bar(2).at, dict(decision=raw[0].at, side=1, stop=99), 0, 2)
        self.assertEqual(result['gross_low'], -3)
        self.assertEqual(result['exit'], 'stop_gap')

    def test_short_side_and_end_of_session_censoring(self):
        raw = [self.bar(0, 100, 100.5, 97, 98)]
        event = dict(decision=raw[0].at, side=-1, stop=101)
        self.assertEqual(execute(raw, 1, self.bar(1).at, event, 0, 1)['gross_low'], 2)
        self.assertEqual(execute(raw, 1, self.bar(1).at, event, 0, 30)['status'],
                         'INSUFFICIENT_SAME_SESSION_HORIZON')

    def test_early_close_dst_grid_and_gzip_are_preserved(self):
        day = '2026-11-27'  # XNYS closes at 13:00 EST.
        start = datetime(2026, 11, 27, 9, 30)
        rows = ['time,open,high,low,close'] + [
            f'{(start+timedelta(minutes=i)).strftime("%H:%M:%S")},100,101,99,100'
            for i in range(0, 210, 5)]
        item = dict(day=day, step=5, csv='\n'.join(rows))
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'data.json.gz'
            p.write_bytes(gzip.compress(json.dumps([item]).encode(), mtime=0))
            sessions, excluded = load_sessions(p)
            self.assertEqual(excluded, [])
            self.assertEqual(len(sessions[0][1]), 42)
            self.assertEqual(sessions[0][-1].hour, 13)
            self.assertEqual(sessions[0][-1].utcoffset(), timedelta(hours=-5))
            item['csv'] = '\n'.join(rows[:-1])
            p.write_bytes(gzip.compress(json.dumps([item]).encode(), mtime=0))
            self.assertEqual(load_sessions(p)[0], [])
            p.write_bytes(gzip.compress(json.dumps([item, item]).encode(), mtime=0))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load_sessions(p)


if __name__ == '__main__':
    unittest.main()
