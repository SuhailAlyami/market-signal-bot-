import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from evaluate_spx_extension import evaluate_segment, inventory, load_history


def frame():
    index = pd.date_range('2026-10-22T13:30Z', periods=390, freq='min')
    close = 7000 + np.arange(390) * .2
    bars = pd.DataFrame(dict(Open=close-.2, High=close+.5, Low=close-2, Close=close), index=index)
    bars.attrs.update(symbol='SPX', security_type='IND')
    return bars


class ExtensionTests(unittest.TestCase):
    def test_segment_keeps_cooldown_from_prior_context(self):
        bars = frame()
        report = evaluate_segment(bars, bars.index[245], 'synthetic_boundary_test')
        signals = report['models']['prelevel_pressure']['signal_matches']['0']
        self.assertTrue(signals)
        # The full-session candidate at240 consumes cooldown until250;
        # incorrectly restarting on the segment would emit at245.
        self.assertEqual(signals[0]['index'], 250)
        self.assertTrue(all(s['index'] >= 245 for s in signals))
        self.assertTrue(report['cooldown_carried_from_session_start'])
        self.assertEqual(report['context_bars_before_segment'], 245)
        self.assertEqual(report['bars_in_segment'], 145)

    def test_coverage_does_not_fill_missing_minute_and_handles_early_close(self):
        bars = frame()
        complete = inventory(bars)
        self.assertTrue(complete[0]['complete'])
        missing = inventory(bars.drop(bars.index[100]))
        self.assertFalse(missing[0]['complete'])
        self.assertEqual(missing[0]['missing_minutes'], ['2026-10-22T15:10:00+00:00'])
        early = bars.iloc[:210].copy()
        early.index = pd.date_range('2026-11-27T14:30Z', periods=210, freq='min')
        self.assertTrue(inventory(early)[0]['complete'])
        self.assertEqual(inventory(early)[0]['expected'], 210)

    def test_original_partial_bar_is_excluded_before_overlap_comparison(self):
        path = Path(__file__).resolve().parents[1] / 'artifacts/spx_only_development/raw.json'
        bars, _, _, excluded = load_history(path)
        self.assertEqual(excluded, 1)
        self.assertEqual(len(bars), 240)
        self.assertEqual(bars.index[-1], pd.Timestamp('2026-10-22T17:29Z'))

    def test_unordered_or_invalid_raw_data_is_rejected(self):
        path = Path(__file__).resolve().parents[1] / 'artifacts/spx_only_development/raw.json'
        payload = json.loads(path.read_text())
        payload['history']['time'][1] = payload['history']['time'][0]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'bad.json'
            output.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, 'unordered_or_unaligned'):
                load_history(output)
