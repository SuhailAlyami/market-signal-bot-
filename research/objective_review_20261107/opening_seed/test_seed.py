import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_seed import (atr_before, detect, detect_seeded, previous_session,  # noqa: E402
                      seeded_atr_before, seeds_for, true_ranges)
from objective_review import Bar, NY  # noqa: E402


def bars(prices, day=(2026, 11, 6)):
    start = datetime(*day, 9, 30, tzinfo=NY)
    return [Bar(start+timedelta(minutes=5*i), p, p+.5, p-.5, p) for i, p in enumerate(prices)]


class OpeningSeedTests(unittest.TestCase):
    def test_identical_to_control_after_six_bars(self):
        source = bars([100+3*((i*7) % 5) for i in range(40)])
        for i in range(6, 40):
            self.assertEqual(seeded_atr_before(source, i, [9]*6), atr_before(source, i))

    def test_seed_window_excludes_decision_bar_and_overnight_gap(self):
        source = bars([100, 300, 100])
        # bar0 contributes high-low only (1.0); decision bar never included.
        self.assertEqual(seeded_atr_before(source, 0, [6]*6), 6)
        self.assertEqual(seeded_atr_before(source, 1, [6]*6), (5*6+1)/6)
        self.assertNotEqual(seeded_atr_before(source, 2, [6]*6), seeded_atr_before(source[:3], 3, [6]*6))

    def test_no_seed_falls_back_to_control(self):
        source = bars([100]*7+[106, 112, 110, 105, 99, 94, 90, 85])
        self.assertEqual(detect_seeded(source, None), detect(source))

    def test_first_possible_signal_at_index1_close(self):
        source = bars([100, 106, 106, 106])
        first = detect_seeded(source, [1]*6)[0]
        self.assertEqual((first['index'], first['side']), (1, 1))
        self.assertEqual(first['decision'], source[0].at+timedelta(minutes=10))
        self.assertEqual(detect(source), [])

    def test_prefix_stability_no_lookahead(self):
        prices = [100, 104, 99, 93, 97, 104, 111, 108, 101, 95, 99, 107, 115, 112, 104, 100]
        full = detect_seeded(bars(prices), [4]*6)
        for k in range(1, len(prices)+1):
            self.assertEqual(detect_seeded(bars(prices[:k]), [4]*6), [s for s in full if s['index'] < k])

    def test_mirror_symmetry(self):
        source = bars([100, 104, 99, 93, 97, 104, 111, 108, 101, 95, 99, 107])
        mirror = [Bar(b.at, 200-b.open, 200-b.low, 200-b.high, 200-b.close) for b in source]
        self.assertEqual([(s['index'], -s['side']) for s in detect_seeded(source, [4]*6)],
                         [(s['index'], s['side']) for s in detect_seeded(mirror, [4]*6)])

    def test_seed_only_from_immediately_preceding_session(self):
        self.assertEqual(previous_session('2026-11-09'), '2026-11-06')
        self.assertEqual(previous_session('2026-08-17'), '2026-08-14')
        mon = bars([100]*10, (2026, 11, 9))
        fri = bars([100]*10, (2026, 11, 6))
        thu = bars([100]*10, (2026, 11, 5))
        seeds = seeds_for([('2026-11-05', thu), ('2026-11-09', mon)])
        self.assertIsNone(seeds['2026-11-09'])  # Friday missing -> no seed, no skipping back
        seeds = seeds_for([('2026-11-05', thu), ('2026-11-06', fri), ('2026-11-09', mon)])
        self.assertEqual(seeds['2026-11-09'], true_ranges(fri)[-6:])
        self.assertEqual(seeds['2026-11-06'], true_ranges(thu)[-6:])


if __name__ == '__main__':
    unittest.main()
