from datetime import timedelta
import unittest

from premium_local_research import GRID, evaluate, local_rule, prepare
from premium_radar import classify
from test_premium_radar import bars

CONFIG = {'lookback':3,'rvol':1.5,'min_return':.015}


class LocalPremiumTests(unittest.TestCase):
    def test_local_turn_can_trigger_below_old_twenty_minute_high(self):
        data = bars(21)
        data.iloc[:17, data.columns.get_loc('High')] = 12.
        data.iloc[20] = [10.,10.7,9.95,10.6,200.]
        f = prepare(data)[20]
        self.assertLess(f['price'], f['prior_high'])
        self.assertTrue(local_rule(f, CONFIG))
        self.assertNotEqual((classify(data,20) or {}).get('state'), 'ACCELERATION')

    def test_prefix_invariance(self):
        data = bars(30)
        data.iloc[20] = [10.,11.1,10.,11.,300.]
        expected = prepare(data.iloc[:21])[20]
        data.iloc[21:] = [100.,110.,90.,105.,100000.]
        self.assertEqual(prepare(data)[20], expected)

    def test_bad_and_inactive_candles_rejected(self):
        for key, value in (('Volume',0),('Close',float('nan')),('Low',-1)):
            data = bars(21)
            data.loc[data.index[-1],key] = value
            self.assertIsNone(prepare(data)[20])

    def test_low_close_within_candle_filters_spike_rejection(self):
        data = bars(21)
        data.iloc[20] = [10.,13.,9.8,10.6,300.]
        self.assertFalse(local_rule(prepare(data)[20], CONFIG))

    def test_delay_is_charged_and_full_event_outcomes_are_not_in_features(self):
        data = bars(35)
        data.iloc[20] = [10.,10.7,9.95,10.6,200.]
        data.iloc[21] = [10.6,10.8,10.5,10.7,100.]
        data.iloc[22] = [10.7,11.6,10.7,11.5,200.]
        data.iloc[23] = [11.5,14.2,11.5,14.,200.]
        prepared = prepare(data)
        fast = evaluate(data,prepared,CONFIG,delay=0)['local']
        slow = evaluate(data,prepared,CONFIG,delay=180)['local']
        self.assertGreater(fast['before_onset'], 0)
        self.assertEqual(slow['before_onset'],0)
        self.assertGreater(fast['within_first_minute_or_before'],slow['within_first_minute_or_before'])

    def test_unobservable_tail_remains_censored(self):
        data = bars(21)
        data.iloc[20] = [10.,10.7,9.95,10.6,200.]
        result = evaluate(data,prepare(data),CONFIG)['local']
        self.assertEqual(result['signals'],0)
        self.assertEqual(result['censored_signals'],1)
        self.assertEqual(result['detected'],0)

    def test_predeclared_grid_is_bounded(self):
        self.assertEqual(len(GRID),8)

    def test_latency_cannot_move_an_earlier_signal_inside_a_later_event(self):
        from unittest.mock import patch
        from research_premium_radar import evaluate as original_evaluate
        data = bars(36)
        data.iloc[20] = [10.,10.7,9.95,10.6,200.]
        data.iloc[21] = [10.6,10.8,10.5,10.7,100.]
        data.iloc[22] = [10.7,11.6,10.7,11.5,200.]
        data.iloc[26] = [10.,14.2,10.,14.,200.]
        only_first=lambda f: f['price']==10.6
        prepared=prepare(data)
        with patch('premium_local_research.local_rule', side_effect=lambda f,c:only_first(f)):
            for delay in (0,60,120):
                self.assertEqual(evaluate(data,prepared,CONFIG,delay)['local']['detected'],0)
                self.assertEqual(original_evaluate(data,delay_seconds=delay,candidate=only_first)['methods']['candidate']['detected_events'],0)
