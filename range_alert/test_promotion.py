import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import promotion as P
import daily_range as D


def market(n, gap, follow, start=date(2026, 11, 13)):
    """n live sessions. Each opens `gap` expected moves away (sign alternating), then SPY follows the gap by
    `follow` dollars (negative = reverses). VIX 16 -> m about 100 SPX points at 7000."""
    spx, vix, spy = {}, {}, {}
    d, pc, sp = start, 7000.0, 700.0
    spx[d.isoformat()] = (pc, pc, pc, pc); vix[d.isoformat()] = (16, 16, 16, 16); spy[d.isoformat()] = (sp,)*4
    for i in range(n):
        d += timedelta(days=1)
        m = pc*16/100/252**0.5
        s = 1 if i % 2 == 0 else -1
        o = pc+s*gap*m
        so = sp+s*gap*m/10
        sc = so+s*follow
        spx[d.isoformat()] = (o, max(o, pc)+20, min(o, pc)-20, pc)   # close back at pc: index flat
        vix[d.isoformat()] = (16,)*4
        spy[d.isoformat()] = (so, so, so, sc)
        sp = sc
    return spx, vix, spy


class GateTests(unittest.TestCase):
    def test_testing_until_enough_trades(self):
        g = P.evaluate(*market(10, 0.6, 1.0), D.K_HIGH, D.K_LOW)
        self.assertEqual(g['trade']['status'], 'TESTING')
        self.assertEqual(g['trade']['n'], 8)   # Nov 14-15 are before LIVE_START

    def test_proven_when_live_pnl_is_robustly_positive(self):
        spx, vix, spy = market(40, 0.6, 1.0)
        spy['2026-11-20'] = spy['2026-11-20'][:3] + (spy['2026-11-20'][0] - 1.0,)   # one losing day
        g = P.evaluate(spx, vix, spy, D.K_HIGH, D.K_LOW)
        self.assertEqual(g['trade']['status'], 'PROVEN')

    def test_failed_when_live_pnl_is_negative(self):
        g = P.evaluate(*market(40, 0.6, -1.0), D.K_HIGH, D.K_LOW)
        self.assertEqual(g['trade']['status'], 'FAILED')

    def test_no_trade_below_threshold_and_research_days_excluded(self):
        g = P.evaluate(*market(40, 0.3, 1.0), D.K_HIGH, D.K_LOW)
        self.assertEqual(g['trade']['n'], 0)
        self.assertTrue(all(r['d'] >= P.LIVE_START for r in P.live_rows(*market(40, 0.6, 1.0))))

    def test_message_follows_status_automatically(self):
        t = D.trade_plan(7000.0, 100.0)
        gate = lambda st: {'trade': {'status': st, 'n': 40, 'wins': 30, 'avg': 4.2, 'total': 168}}
        self.assertIn('غير مثبتة', '\n'.join(D.trade_lines(t, gate('TESTING'))))
        self.assertIn('التوصية', '\n'.join(D.trade_lines(t, gate('PROVEN'))))
        failed = '\n'.join(D.trade_lines(t, gate('FAILED')))
        self.assertIn('أُوقفت', failed)
        self.assertNotIn('7,050', failed)
        self.assertIn('غير مثبتة', '\n'.join(D.trade_lines(t)))      # gate unavailable -> safe default

    def test_record_line_and_level_calibration(self):
        g = P.evaluate(*market(25, 0.6, 1.0), D.K_HIGH, D.K_LOW)
        self.assertIn('السجل الحي', P.record_line(g))
        self.assertEqual(set(g['levels']), {'high', 'low', 'range'})

    def test_wilson_bounds(self):
        lo, hi = P.wilson(30, 40)
        self.assertTrue(0.5 < lo < 0.75 < hi < 0.9)


if __name__ == '__main__':
    unittest.main()
