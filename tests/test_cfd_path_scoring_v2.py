import unittest
from cfd_path_scoring_v2 import outcome


class PathOrderTests(unittest.TestCase):
    def test_known_open_precedes_later_extremes_for_both_directions(self):
        fixtures = [(1, 101.1, 102, 98, 'target'),
                    (1, 99.2, 102, 98, 'stop'),
                    (-1, 98.9, 102, 98, 'target'),
                    (-1, 100.8, 102, 98, 'stop')]
        for sign, opening, high, low, expected in fixtures:
            with self.subTest(sign=sign, opening=opening):
                self.assertEqual(outcome(sign,100,1,opening,high,low), expected)

    def test_unknown_intrabar_order_stays_ambiguous(self):
        for sign in (-1,1):
            self.assertEqual(outcome(sign,100,1,100,102,98), 'ambiguous')

    def test_single_touch_and_no_touch_are_distinguished(self):
        self.assertEqual(outcome(1,100,1,100,101.1,99.9), 'target')
        self.assertEqual(outcome(1,100,1,100,100.1,99.1), 'stop')
        self.assertEqual(outcome(-1,100,1,100,100.1,98.9), 'target')
        self.assertEqual(outcome(-1,100,1,100,100.8,99.9), 'stop')
        self.assertEqual(outcome(1,100,1,100,100.1,99.9), 'pending')

    def test_invalid_observations_are_not_repaired(self):
        for args in [(0,100,1,100,101,99), (1,100,0,100,101,99),
                     (1,100,1,100,99,98), (1,100,1,float('nan'),101,99)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                outcome(*args)


if __name__ == '__main__':
    unittest.main()
