import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent/'wave_capture'))
from run_scale import detect_scaled  # noqa: E402
from run import detect  # noqa: E402
from objective_review import Bar, NY  # noqa: E402


def bars(prices):
    s = datetime(2026, 11, 6, 9, 30, tzinfo=NY)
    return [Bar(s+timedelta(minutes=5*i), p, p+1.5, p-1.5, p) for i, p in enumerate(prices)]


class ScaleTests(unittest.TestCase):
    def setUp(self):
        self.p = [100+8*((i*5) % 7)-12*((i*3) % 4) for i in range(60)]

    def test_k1_reproduces_control_exactly(self):
        self.assertEqual(detect_scaled(bars(self.p), 1.0), detect(bars(self.p)))

    def test_smaller_k_never_signals_later_on_first_event(self):
        a, b = detect(bars(self.p)), detect_scaled(bars(self.p), .67)
        self.assertTrue(b and a)
        self.assertLessEqual(b[0]['index'], a[0]['index'])

    def test_prefix_stability_no_lookahead(self):
        full = detect_scaled(bars(self.p), .67)
        for n in (12, 25, 40, 60):
            self.assertEqual(detect_scaled(bars(self.p[:n]), .67), [s for s in full if s['index'] < n])

    def test_mirror_symmetry(self):
        b = bars(self.p)
        m = [Bar(x.at, 200-x.open, 200-x.low, 200-x.high, 200-x.close) for x in b]
        self.assertEqual([(s['index'], -s['side']) for s in detect_scaled(b, .67)], [(s['index'], s['side']) for s in detect_scaled(m, .67)])


if __name__ == '__main__':
    unittest.main()
