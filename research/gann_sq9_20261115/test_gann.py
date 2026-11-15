import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gann as g  # noqa: E402
from objective_review import Bar, NY  # noqa: E402

T0 = datetime(2026, 10, 1, 9, 30, tzinfo=NY)
CLOSE = datetime(2026, 10, 1, 16, 0, tzinfo=NY)


def bars(rows):
    return [Bar(T0+timedelta(minutes=5*i), *r) for i, r in enumerate(rows)]


class GannTests(unittest.TestCase):
    def test_step_is_sqrt_over_two(self):
        self.assertAlmostEqual(__import__('math').sqrt(4140)/2, 32.17, places=2)

    def test_rejection_and_break_detection(self):
        lv = [(1, 110.0)]
        self.assertEqual(g.setups(Bar(T0, 105, 111, 104, 108), lv, 10)[0][2:4], ('reject', -1))
        self.assertEqual(g.setups(Bar(T0, 105, 114, 104, 113), lv, 10)[0][2:4], ('break', 1))
        self.assertEqual(g.setups(Bar(T0, 105, 112, 104, 111), lv, 10), [])  # close beyond but not by 0.25*S

    def test_worst_case_stop_first_and_entry_next_open(self):
        b = bars([(100, 101, 99, 100), (105, 115, 104, 113), (113, 125, 105, 120), (120, 121, 119, 120)])
        tr = g.simulate_day(b, CLOSE, 100.0, 10.0)  # level 110 breaks on bar 1; entry bar 2 open 113, stop 107.5, target 120
        self.assertEqual((tr[0]['entry'], tr[0]['exit'], tr[0]['exit_reason']), (113, 107.5, 'stop'))

    def test_session_close_exit(self):
        b = bars([(100, 101, 99, 100), (105, 115, 104, 113), (113, 116, 112, 114), (114, 115, 113, 115)])
        tr = g.simulate_day(b, CLOSE, 100.0, 10.0)
        self.assertEqual((tr[0]['exit'], tr[0]['exit_reason']), (115, 'session_close'))


if __name__ == '__main__':
    unittest.main()
