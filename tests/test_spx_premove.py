import json
from pathlib import Path
import unittest

import pandas as pd

from research_spx_premove import MODELS, features, signal_schedule, preanchor_diagnostic


class PremoveCausalityTests(unittest.TestCase):
    def fixture(self):
        path = Path(__file__).resolve().parents[1]/'artifacts/spx_only_development/raw.json'
        h = json.loads(path.read_text())['history']
        bars = pd.DataFrame({k:h[k.lower()] for k in ('Open','High','Low','Close')},
                            index=pd.to_datetime(h['time'], utc=True)).iloc[:240].copy()
        bars.attrs.update(symbol='SPX', security_type='IND')
        return bars

    def test_every_model_keeps_prefix_decisions_when_future_prices_change(self):
        bars = self.fixture()
        changed = bars.copy()
        changed.iloc[120:] = changed.iloc[120:]+100
        original_features, changed_features = features(bars), features(changed)
        for model in MODELS:
            original = [s for s in signal_schedule(original_features, model) if s['index'] < 120]
            actual = [s for s in signal_schedule(changed_features, model) if s['index'] < 120]
            self.assertEqual(original, actual, model)
        self.assertNotIn('Volume', bars)

    def test_preanchor_diagnostic_requires_early_delivery_and_target_in_horizon(self):
        bars = self.fixture()
        signal = dict(index=40, direction=1,
                      detected_at=(bars.index[40]+pd.Timedelta(minutes=1)).isoformat())
        event = dict(event_id=0, direction=1, anchor_index=42, target_index=48,
                     onset_time=bars.index[43].isoformat())
        self.assertEqual(preanchor_diagnostic([event],[signal],bars)['early_matches'],1)
        self.assertEqual(preanchor_diagnostic([event],[signal],bars,delay=2)['early_matches'],0)
        event['target_index'] = 52
        self.assertEqual(preanchor_diagnostic([event],[signal],bars)['early_matches'],0)


if __name__ == '__main__':
    unittest.main()
