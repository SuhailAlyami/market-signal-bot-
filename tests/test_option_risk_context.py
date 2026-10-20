import unittest
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from option_risk_context import VolatilityObservation, compare_volatility, long_option_context
from spx_option_selector import OptionQuote, select_spx_0dte

NOW = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)

class VolatilityContextTests(unittest.TestCase):
    def setUp(self):
        self.iv = VolatilityObservation(.135, 'SPX', NOW, 'documented feed', 'calendar_365', 30)
        self.rv = replace(self.iv, annualized_decimal=.108)

    def test_comparison_is_not_entry_or_probability(self):
        result = compare_volatility(self.iv, self.rv, now=NOW)
        self.assertAlmostEqual(result['iv_to_rv'], 1.25)
        self.assertAlmostEqual(result['iv_minus_rv_percentage_points'], 2.7)
        self.assertFalse(result['entry_signal'])
        self.assertNotIn('profit_probability', result)

    def test_unknown_mismatched_stale_values_never_produce_comparison(self):
        variants = [None, replace(self.rv, basis='unknown'), replace(self.rv, basis='trading_252'),
                    replace(self.rv, horizon_days=1), replace(self.rv, underlying='ES'),
                    replace(self.rv, annualized_decimal=float('nan')),
                    replace(self.rv, annualized_decimal=0), replace(self.rv, source=''),
                    replace(self.rv, as_of=NOW-timedelta(seconds=61)),
                    replace(self.rv, as_of=NOW+timedelta(seconds=1))]
        for rv in variants:
            with self.subTest(rv=rv):
                result = compare_volatility(self.iv, rv, now=NOW)
                self.assertEqual(result['status'], 'UNAVAILABLE')
                self.assertNotIn('iv_to_rv', result)

    def test_otm_call_and_put_use_ask_expiry_payoff_not_intraday_target(self):
        call = long_option_context(right='C', strike=7750, underlying=7692, ask=4)
        put = long_option_context(right='P', strike=7650, underlying=7692, ask=3)
        self.assertEqual(call['otm_distance_points'], 58)
        self.assertEqual(call['expiry_breakeven_before_fees'], 7754)
        self.assertEqual(call['favorable_move_to_expiry_breakeven_points'], 62)
        self.assertEqual(put['expiry_breakeven_before_fees'], 7647)
        self.assertEqual(put['favorable_move_to_expiry_breakeven_points'], 45)
        self.assertEqual(call['maximum_premium_loss_usd_before_fees'], 400)
        self.assertIsNone(call['profit_probability'])

    def test_context_cannot_bypass_live_book_or_change_atm_ranking(self):
        quotes = [OptionQuote('SPX','2026-10-20','C',7700,2,2.1,NOW,'feed',True),
                  OptionQuote('SPX','2026-10-20','C',7690,4,4.1,NOW,'feed',True, implied_volatility=self.iv, realized_volatility=self.rv)]
        kw = dict(direction='CALL', underlying=7692, underlying_time=NOW, now=NOW,
                  underlying_live_verified=True)
        result = select_spx_0dte(quotes, **kw)
        self.assertEqual(result.strike, 7690)
        self.assertFalse(result.risk_context['entry_signal'])
        self.assertEqual(result.risk_context['volatility_comparison']['status'], 'OBSERVED')
        self.assertEqual(result.risk_context['expiry_breakeven_before_fees'], 7694.1)
        kw['underlying_live_verified'] = False
        self.assertIsNone(select_spx_0dte(quotes, **kw))

    def test_invalid_payoff_inputs_rejected(self):
        for value in (float('nan'), 0, -1, float('inf')):
            with self.assertRaises(ValueError):
                long_option_context(right='C', strike=value, underlying=7692, ask=4)
