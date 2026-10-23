import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from collect_spx_sessions import request_end, sessions
from evaluate_spx_sessions import (
    BASELINES, HYPOTHESES, MODELS, chronological_days, early_f1,
    evaluate_partition, load_capture, quality_gate, select_training, study,
)


def metric(good=False):
    return dict(precision=.8 if good else .1,
                precision_wilson_95=[.6, .9] if good else [.01, .2],
                early_precision=.6 if good else 0,
                early_event_recall=.4 if good else 0,
                median_lead_minutes=2 if good else -1,
                false_alarms_per_session=1 if good else 8,
                false_alarms=1 if good else 8)


class ChronologicalStudyTests(unittest.TestCase):
    def days(self):
        return [day for day, _, _ in sessions('2026-10-21', 20, now='2026-10-22T00:00Z')]

    def test_whole_session_split_sizes_disjoint_ordered_and_minimum(self):
        days = self.days()
        split = chronological_days(days)
        self.assertEqual([len(split[k]) for k in ('train', 'validation', 'holdout')], [12, 4, 4])
        self.assertLess(max(split['train']), min(split['validation']))
        self.assertLess(max(split['validation']), min(split['holdout']))
        with self.assertRaisesRegex(ValueError, '20_independent'):
            chronological_days(days[:-1])

    def test_validation_failure_never_evaluates_holdout_or_other_parameters(self):
        days, calls = self.days(), []
        selected = HYPOTHESES[1]

        def evaluate(dataset, evaluated_days, models):
            calls.append((evaluated_days, models))
            if evaluated_days == days[16:]:
                raise AssertionError('holdout opened after failed validation')
            scores = {model: {'strict': {'0': metric()}} for model in models}
            if evaluated_days == days[:12]:
                scores[selected]['strict']['0'] = metric(True)
            return {'models': scores}

        with patch('evaluate_spx_sessions.evaluate_partition', side_effect=evaluate):
            report = study(dict.fromkeys(days), [], 'test-digest')
        self.assertEqual(report['model_selected'], selected)
        self.assertFalse(report['holdout_opened'])
        self.assertNotIn('holdout', report)
        self.assertEqual(calls, [(days[:12], MODELS), (days[12:16], (selected, *BASELINES))])

    def test_validation_pass_opens_only_selected_model_and_fixed_baselines(self):
        days, calls = self.days(), []
        chosen = HYPOTHESES[0]

        def evaluate(dataset, evaluated_days, models):
            calls.append((evaluated_days, models))
            return {'models': {model: {'strict': {'0': metric(model == chosen)}} for model in models}}

        with patch('evaluate_spx_sessions.evaluate_partition', side_effect=evaluate):
            report = study(dict.fromkeys(days), [], 'test-digest')
        self.assertEqual(calls[-1], (days[16:], (chosen, *BASELINES)))
        self.assertTrue(report['holdout_opened'])
        self.assertTrue(report['accepted'])
        self.assertFalse(report['notifications_enabled'])
        self.assertFalse(report['orders_enabled'])

    def test_training_selection_uses_early_not_any_directional_hit(self):
        models = {model: {'strict': {'0': metric()}} for model in HYPOTHESES}
        models[HYPOTHESES[0]]['strict']['0']['precision'] = 1
        models[HYPOTHESES[2]]['strict']['0'] = metric(True)
        self.assertEqual(select_training(models), HYPOTHESES[2])
        failed = metric(True)
        failed['precision_wilson_95'] = [.39, .99]
        self.assertFalse(quality_gate(failed)['passed'])

    def test_partition_label_horizon_never_crosses_close(self):
        # Synthetic transport/research fixture; no market-quality claims.
        days = self.days()[:2]
        dataset = {}
        for day in days:
            _, opened, closed = sessions(day, 1, now='2026-10-22T00:00Z')[0]
            times = pd.date_range(opened, closed, freq='min', inclusive='left')
            base = pd.Series(range(len(times)), index=times) * .5 + 7000
            bars = pd.DataFrame(dict(Open=base, High=base+1, Low=base-1, Close=base+.4))
            bars.attrs.update(symbol='SPX', security_type='IND')
            dataset[day] = bars
        with patch('evaluate_spx_sessions.score_signals', wraps=__import__('hunter_research').score_signals) as scorer:
            report = evaluate_partition(dataset, days, ('no_signal',))
        for event in report['events']:
            self.assertEqual(event['anchor_time'][:10], event['target_time'][:10])
        self.assertEqual(report['models']['no_signal']['strict']['0']['sessions'], 2)
        self.assertEqual(report['models']['no_signal']['strict']['0']['signals'], 0)
        self.assertEqual(scorer.call_count, 3)


class RawCaptureIntegrityTests(unittest.TestCase):
    def build_capture(self, directory, count=1):
        plan = sessions('2026-10-21', count, now='2026-10-22T00:00Z')
        root = dict(symbol='SPX', security_type='IND', exchange='CBOE', currency='USD', contract_id=123)
        manifest = dict(source='IBKR_TWS_API_HISTORY', contract=root,
                        data_complete=True, requested_sessions=count, sessions=[])
        for day, opened, closed in plan:
            raw = dict(contract=root, received_at='2026-10-22T00:00:00+00:00',
                       request=dict(endDateTime=request_end(closed), durationStr='1 D',
                                    barSizeSetting='1 min', whatToShow='TRADES', useRTH=1,
                                    formatDate=2, keepUpToDate=False),
                       provider_bounds={'start': 'original', 'end': 'original'},
                       rows=[dict(time=str(int(t.timestamp())), open=7000, high=7001,
                                  low=6999, close=7000, volume='-1')
                             for t in pd.date_range(opened, closed, freq='min', inclusive='left')])
            encoded = json.dumps(raw).encode()
            (directory / f'{day}.raw.json').write_bytes(encoded)
            manifest['sessions'].append(dict(date=day, raw_sha256=hashlib.sha256(encoded).hexdigest()))
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_hash_verified_raw_not_validated_summary_is_authoritative(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.build_capture(directory)
            data, inventory, digest = load_capture(directory)
            self.assertEqual(len(data['2026-10-21']), 390)
            self.assertTrue(inventory[0]['complete'])
            self.assertEqual(len(digest), 64)
            path = directory / '2026-10-21.raw.json'
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'raw_hash_mismatch'):
                load_capture(directory)

    def test_missing_raw_minute_rejected_even_when_manifest_claims_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            manifest = self.build_capture(directory)
            path = directory / '2026-10-21.raw.json'
            raw = json.loads(path.read_text())
            raw['rows'].pop(100)
            encoded = json.dumps(raw).encode()
            path.write_bytes(encoded)
            manifest['sessions'][0]['raw_sha256'] = hashlib.sha256(encoded).hexdigest()
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'incomplete_capture'):
                load_capture(directory)

    def test_consumed_session_is_rejected_before_reading_prices(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            manifest = self.build_capture(directory)
            manifest['sessions'][0]['date'] = '2026-10-22'
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'consumed_or_later'):
                load_capture(directory)


if __name__ == '__main__':
    unittest.main()
