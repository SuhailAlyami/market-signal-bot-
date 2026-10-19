import unittest
from datetime import datetime, timedelta, timezone
from spx_option_selector import OptionQuote, select_spx_0dte

NOW = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)

def quote(**kw):
    args = dict(symbol="SPX", expiry="2026-10-19", right="C", strike=5800,
                bid=8.0, ask=8.5, quote_time=NOW, source="verified_feed",
                live_verified=True)
    args.update(kw)
    return OptionQuote(**args)

def pick(quotes, **kw):
    args = dict(direction="CALL", underlying=5801.0, underlying_time=NOW,
                now=NOW, underlying_live_verified=True)
    args.update(kw)
    return select_spx_0dte(quotes, **args)

class SelectorTests(unittest.TestCase):
    def test_selects_real_nearest_atm(self):
        result = pick([quote(strike=5820), quote()])
        self.assertEqual(result.strike, 5800)
        self.assertEqual(result.mid, 8.25)
        self.assertTrue(result.research_only)

    def test_missing_feed_fails_closed(self):
        self.assertIsNone(pick([]))
        self.assertIsNone(pick([quote()], underlying_live_verified=False))
        self.assertIsNone(pick([quote(live_verified=False)]))
        self.assertIsNone(pick([quote(source="")]))

    def test_stale_and_future_fail_closed(self):
        self.assertIsNone(pick([quote(quote_time=NOW-timedelta(seconds=11))]))
        self.assertIsNone(pick([quote(quote_time=NOW+timedelta(seconds=1))]))
        self.assertIsNone(pick([quote()], underlying_time=NOW-timedelta(seconds=11)))

    def test_wrong_contract_or_bad_market_fails_closed(self):
        for changes in [dict(expiry="2026-10-20"), dict(symbol="SPY"),
                        dict(right="P"), dict(ask=11), dict(bid=0),
                        dict(strike=6000), dict(multiplier=10)]:
            with self.subTest(changes=changes):
                self.assertIsNone(pick([quote(**changes)]))

    def test_invalid_thresholds_fail_closed(self):
        for changes in [dict(max_age_seconds=-1), dict(max_age_seconds=float("nan")),
                        dict(max_spread_pct=float("nan")),
                        dict(max_moneyness_pct=float("nan"))]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                pick([quote()], **changes)

    def test_put_side(self):
        self.assertEqual(pick([quote(right="P")], direction="PUT").right, "P")

    def test_timezone_boundary(self):
        with self.assertRaises(ValueError):
            pick([quote()], now=datetime(2026, 10, 19, 15, 0))

if __name__ == "__main__":
    unittest.main()
