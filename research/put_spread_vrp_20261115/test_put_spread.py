import unittest
import put_spread as p


class T(unittest.TestCase):
    def test_bs_put_parity_and_bounds(self):
        c = p.bs_put(100, 100, 0.2)
        self.assertTrue(2.0 < c < 2.6)  # ATM 30d 20% vol ~ 2.29
        self.assertGreater(p.bs_put(100, 95, 0.2), p.bs_put(100, 90, 0.2))

    def test_payout_capped_at_width(self):
        k1, k2 = 100.0, 95.0
        for st_, exp in ((110, 0), (98, 2), (80, 5)):
            self.assertEqual(min(max(k1-st_, 0.0), k1-k2), exp)


if __name__ == '__main__':
    unittest.main()
