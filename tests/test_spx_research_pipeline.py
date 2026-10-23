import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collect_spx_sessions import sessions
from evaluate_spx_sessions import PROTOCOL_COMMIT, reserve_holdout, run_capture
from run_spx_research import run


def passing_partition(dataset, days, models):
    return {'models': {name: {'strict': {'0': dict(
        precision=.8, precision_wilson_95=[.6, .9], early_precision=.6,
        early_event_recall=.4, median_lead_minutes=2,
        false_alarms_per_session=1, false_alarms=1)}} for name in models}}


class HoldoutPersistenceTests(unittest.TestCase):
    def dataset(self):
        return dict.fromkeys(day for day, _, _ in
                             sessions('2026-10-21', 20, now='2026-10-22T00:00Z'))

    def test_new_output_or_recapture_digest_cannot_reopen_same_holdout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = self.dataset()
            with (patch('evaluate_spx_sessions.load_capture', return_value=(dataset, [], 'digest-one')),
                    patch('evaluate_spx_sessions.evaluate_partition', side_effect=passing_partition) as evaluate):
                first = run_capture('fake', root / 'one.json', root / 'registry')
                self.assertTrue(first['holdout_opened'])
                self.assertEqual(evaluate.call_count, 3)
            with (patch('evaluate_spx_sessions.load_capture', return_value=(dataset, [], 'different-receipt-digest')),
                    patch('evaluate_spx_sessions.evaluate_partition', side_effect=passing_partition) as evaluate):
                second = run_capture('fake', root / 'two.json', root / 'registry')
                self.assertFalse(second['holdout_opened'])
                self.assertTrue(second['holdout_previously_reserved'])
                self.assertEqual(evaluate.call_count, 2)

    def test_failed_holdout_evaluation_stays_consumed_and_report_says_opened(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = self.dataset()
            holdout = list(dataset)[16:]

            def evaluate(data, days, models):
                if days == holdout:
                    # Report checkpoint must exist BEFORE outcomes are evaluated.
                    checkpoint = json.loads((root / 'report.json').read_text())
                    self.assertTrue(checkpoint['holdout_opened'])
                    raise RuntimeError('private text must not be recorded')
                return passing_partition(data, days, models)

            with (patch('evaluate_spx_sessions.load_capture', return_value=(dataset, [], 'digest')),
                    patch('evaluate_spx_sessions.evaluate_partition', side_effect=evaluate)):
                report = run_capture('fake', root / 'report.json', root / 'registry')
            self.assertTrue(report['holdout_opened'])
            self.assertEqual(report['reason'], 'holdout_evaluation_failed_session_consumed')
            self.assertNotIn('private text', (root / 'report.json').read_text())
            for day in holdout:
                self.assertTrue((root / 'registry' / PROTOCOL_COMMIT / f'{day}.json').exists())

    def test_prior_holdout_cannot_later_be_used_for_training(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = self.dataset()
            reserve_holdout([list(dataset)[0]], 'old', root / 'registry')
            with (patch('evaluate_spx_sessions.load_capture', return_value=(dataset, [], 'new')),
                    patch('evaluate_spx_sessions.evaluate_partition') as evaluate):
                report = run_capture('fake', root / 'report.json', root / 'registry')
            self.assertEqual(report['reason'], 'previous_holdout_in_training_or_validation')
            evaluate.assert_not_called()

    def test_validation_failure_does_not_create_reservations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = self.dataset()

            def failing(data, days, models):
                report = passing_partition(data, days, models)
                for model in report['models'].values():
                    model['strict']['0']['precision'] = 0
                return report

            with (patch('evaluate_spx_sessions.load_capture', return_value=(dataset, [], 'digest')),
                    patch('evaluate_spx_sessions.evaluate_partition', side_effect=failing)):
                report = run_capture('fake', root / 'report.json', root / 'registry')
            self.assertFalse(report['holdout_opened'])
            self.assertFalse((root / 'registry').exists())

    def test_overlapping_holdout_reservation_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            reserve_holdout(['2026-10-20', '2026-10-21'], 'first', temp)
            with self.assertRaisesRegex(ValueError, 'already_reserved'):
                reserve_holdout(['2026-10-21'], 'second', temp)


class SingleCommandTests(unittest.TestCase):
    def test_incomplete_capture_never_starts_study(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'new-run'
            with (patch('run_spx_research.collect', return_value={'data_complete': False, 'failure': 'missing_history'}) as collect,
                    patch('run_spx_research.run_capture') as evaluate):
                result = run(output)
            evaluate.assert_not_called()
            collect.assert_called_once_with('2026-10-21', 20, output / 'capture', 4001, 20331025)
            self.assertFalse(result['accepted'])
            self.assertFalse(result['holdout_opened'])
            self.assertTrue((output / 'study.json').exists())

    def test_complete_capture_runs_evaluator_and_preserves_negative_result(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'new-run'
            negative = dict(accepted=False, readiness='NOT_READY', reason='validation_failed_holdout_not_evaluated')
            with (patch('run_spx_research.collect', return_value={'data_complete': True}),
                    patch('run_spx_research.run_capture', return_value=negative) as evaluate):
                result = run(output)
            evaluate.assert_called_once_with(output / 'capture', output / 'study.json')
            self.assertFalse(result['accepted'])


if __name__ == '__main__':
    unittest.main()
