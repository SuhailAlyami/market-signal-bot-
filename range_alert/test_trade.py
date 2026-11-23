import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_range as D
import evaluate_range as E


class TradeTests(unittest.TestCase):
    def test_open_odds_are_the_tradable_numbers_not_the_prev_close_ones(self):
        self.assertEqual(D.open_odds(-0.6), (41, 59))
        self.assertEqual(D.open_odds(0.0), (54, 46))
        self.assertEqual(D.open_odds(0.7), (61, 39))
        for g in (-3, -0.5, -0.2, 0.2, 0.5, 3):
            self.assertIsNotNone(D.open_odds(g))

    def test_plan_levels_are_half_an_expected_move(self):
        t = D.trade_plan(7000.0, 100.0)
        self.assertEqual((t['long_above'], t['short_below']), (7050.0, 6950.0))
        text = '\n'.join(D.trade_lines(t))
        self.assertIn('7,050', text)
        self.assertIn('6,950', text)
        self.assertIn('غير مثبتة', text)

    def test_score_trade_long_short_and_no_trade(self):
        c = {'trade': D.trade_plan(7000.0, 100.0)}
        self.assertEqual(E.score_trade(c, 7060, 7080), 20)      # opened above -> long
        self.assertEqual(E.score_trade(c, 6940, 6900), 40)      # opened below -> short
        self.assertEqual(E.score_trade(c, 6940, 6990), -50)
        self.assertIsNone(E.score_trade(c, 7010, 7100))         # inside: no trade
        self.assertIsNone(E.score_trade({}, 7060, 7080))         # old calls without a plan


if __name__ == '__main__':
    unittest.main()
