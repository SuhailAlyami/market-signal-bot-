import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from hunter_runtime import HunterRuntime
from price_action_context import observe


def fixture():
    return pd.DataFrame(dict(Open=100., High=101., Low=99., Close=100., Volume=100.),
                        index=pd.date_range('2026-10-22T14:00Z', periods=40, freq='min'))


class ContextTests(unittest.TestCase):
    def test_reclaim_requires_completed_close_and_both_sides_are_ambiguous(self):
        data = fixture()
        data.loc[data.index[-1], ['Low', 'Close']] = [98., 99.5]
        result = observe(data, 39)
        self.assertEqual(result['sweep_direction'], 'UP')
        self.assertEqual(result['swept_extreme'], 98.)
        self.assertEqual(result['opposite_liquidity_reference'], 101.)
        data.loc[data.index[-1], 'Close'] = 99.  # exact touch is not reclaim
        self.assertIsNone(observe(data, 39)['sweep_direction'])
        data.loc[data.index[-1], ['High', 'Close']] = [102., 100.]
        self.assertEqual(observe(data, 39)['sweep_direction'], 'AMBIGUOUS')

    def test_three_candle_gap_and_first_close_inversion_only(self):
        data = fixture()
        data.iloc[-3, :4] = [97., 98., 96., 97.]  # bearish gap vs candle -5
        data.iloc[-2, :4] = [97., 98., 96., 97.]
        result = observe(data, 39)
        self.assertEqual(result['inversion_direction'], 'UP')
        self.assertEqual(result['inversion_zone'], [98., 99.])
        self.assertEqual(result['gap_direction'], 'UP')
        data.iloc[-2, :4] = [100., 101., 99., 100.]
        self.assertIsNone(observe(data, 39)['inversion_direction'])

    def test_future_bars_cannot_change_past_evidence_or_mutate_input(self):
        data = fixture(); before = data.copy(deep=True)
        observed = observe(data, 35)
        pd.testing.assert_frame_equal(data, before)
        data.iloc[36:, :4] = [999., 1000., 998., 999.]
        self.assertEqual(observe(data, 35), observed)

    def test_missing_history_gaps_bad_prices_and_missing_index_volume(self):
        data = fixture()
        self.assertEqual(observe(data, 20)['status'], 'unavailable')
        broken = data.drop(data.index[-2])
        self.assertEqual(observe(broken, len(broken)-1)['reason'], 'noncontiguous_or_naive_bars')
        data.iloc[-1, data.columns.get_loc('Close')] = float('nan')
        self.assertEqual(observe(data, 39)['reason'], 'invalid_ohlc')
        result = observe(fixture().drop(columns='Volume'), 39)
        self.assertEqual(result['status'], 'observed')
        self.assertFalse(result['notify_eligible']); self.assertFalse(result['complete_pdf_setup'])
        self.assertEqual(result['volume_profile_status'], 'unavailable_trade_volume_at_price')

    def test_annotations_and_errors_cannot_change_live_events(self):
        data = fixture(); now = data.index[-1].to_pydatetime()
        def detector(*args):
            return dict(direction=1, price=100., atr=2., level=101., invalidation=98., rvol=1.5)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = HunterRuntime(root/'a.json', root/'a.jsonl', symbols=('ES=F',), detector=detector)
            failed = HunterRuntime(root/'b.json', root/'b.jsonl', symbols=('ES=F',), detector=detector)
            events = baseline._process_bar('ES=F', data, 39, now)
            with patch('price_action_context.observe', side_effect=RuntimeError('fixture')):
                same_events = failed._process_bar('ES=F', data, 39, now)
            self.assertEqual(events, same_events)
            self.assertEqual(baseline.state, failed.state)
            observation = json.loads((root/'a.jsonl').read_text(encoding='utf-8').splitlines()[-1])
            self.assertEqual(observation['price_action_context']['mode'], 'SHADOW')
            error = json.loads((root/'b.jsonl').read_text(encoding='utf-8').splitlines()[-1])
            self.assertEqual(error['price_action_context']['status'], 'context_error')


if __name__ == '__main__':
    unittest.main()
