import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from diagnose_spx_misses import diagnose


class MissDiagnosisTests(unittest.TestCase):
    def test_consumed_fixture_preserves_baseline_and_accounts_for_every_event(self):
        root = Path(__file__).resolve().parents[1]
        raw = root/'artifacts/spx_only_development/raw.json'
        baseline = json.loads((root/'artifacts/spx_only_development/report.json').read_text())
        before = hashlib.sha256(raw.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            result = diagnose(raw, Path(directory)/'diagnosis.json', baseline['protocol_commit'])
        self.assertEqual(result['input_sha256'], before)
        self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), before)
        self.assertEqual(sum(result['attribution_counts'].values()), result['events'])
        for name in ('watch', 'confirmation'):
            current = result['metrics_with_delivery_delay_minutes'][name]['0']
            for key in ('signals', 'matched_events', 'early_matched_events', 'false_alarms'):
                self.assertEqual(current[key], baseline['metrics'][name][key])
        for row in result['event_attribution']:
            for s in row['early_raw_candidates']:
                self.assertGreaterEqual(s['index'], row['anchor_index'])
                self.assertLess(s['index'], row['target_index'])
                self.assertLess(s['detected_at'], row['onset_time'])
        self.assertFalse(result['holdout'])
        self.assertFalse(result['detector_changed'])
        self.assertFalse(result['notifications_enabled'])


if __name__ == '__main__':
    unittest.main()
