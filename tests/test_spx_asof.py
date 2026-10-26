from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from spx_availability_recorder import Trace
from spx_asof import AsOfTrace, diagnose

UTC = timezone.utc


class AsOfTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.opened = datetime(2026, 10, 23, 13, 30, tzinfo=UTC)
        self.closed = self.opened + timedelta(minutes=40)
        trace = Trace(self.root, '2026-10-23', self.opened, self.closed,
                      now=self.opened-timedelta(seconds=10))
        trace.contract_id = 416904
        trace.emit('subscriptions', now=self.opened, contract_id=416904)
        trace.set_mode(1, now=self.opened)
        for minute in range(40):
            trace.bar(self.bar(minute), live=True,
                      now=self.opened+timedelta(minutes=minute+1, seconds=2))
        trace.close()
        self.path = trace.path
        self.events = [json.loads(line) for line in self.path.read_text().splitlines()]

    def tearDown(self):
        self.directory.cleanup()

    def bar(self, minute, close=100.):
        return dict(time=int((self.opened+timedelta(minutes=minute)).timestamp()),
                    open=100., high=max(100.2, close), low=min(99.8, close), close=close)

    def model(self, events=None):
        return AsOfTrace(events or self.events, self.opened, self.closed)

    def test_prefix_future_poison_and_later_revision_do_not_change_prior_decision(self):
        decision_at = self.opened+timedelta(minutes=31, seconds=2)
        prior = self.model().decision(decision_at)
        changed = deepcopy(self.events)
        for event in changed:
            if event['received_at'] > decision_at.isoformat() and 'bar' in event:
                event['bar'].update(high=10000., close=9999.)
        changed.append(dict(kind='historical_update', connection=changed[-1]['connection'],
                            received_at=(self.closed+timedelta(seconds=5)).isoformat(),
                            bar=self.bar(30, 103.), parallel_quote_mode=1))
        self.assertEqual(prior, self.model(changed).decision(decision_at))
        prefix = [e for e in self.events if e['received_at'] <= decision_at.isoformat()]
        self.assertEqual(prior, self.model(prefix).decision(decision_at))
        frame, status = self.model(changed).snapshot(self.closed+timedelta(seconds=6))
        self.assertEqual(frame.iloc[30].Close, 103.)
        self.assertEqual(status, 'ok')

    def test_incomplete_backfill_and_standalone_clock_never_create_availability(self):
        events = [e for e in self.events if e['kind'] not in ('first_completed_observation', 'historical_update')]
        connection = events[-1]['connection']
        events += [dict(kind='historical_backfill', connection=connection,
                        received_at=self.closed.isoformat(), bar=self.bar(i)) for i in range(40)]
        events.append(dict(kind='quote_callback', connection=connection,
                           received_at=self.closed.isoformat(), tick_type=45,
                           value=int(self.closed.timestamp())))
        self.assertEqual(len(self.model(events).snapshot(self.closed)[0]), 0)
        self.assertEqual(self.model(events).snapshot(self.closed)[1], 'warming_up_or_gap')

    def test_unknown_delayed_mode_and_clock_regression_rejected(self):
        for mode in (None, 2, 3, 4):
            cutoff = self.opened+timedelta(minutes=31, seconds=2)
            events = deepcopy([e for e in self.events if e['received_at'] <= cutoff.isoformat()])
            events.append(dict(kind='market_data_type', connection=events[-1]['connection'],
                               received_at=(cutoff+timedelta(seconds=1)).isoformat(),
                               market_data_type=mode))
            self.assertEqual(self.model(events).decision(cutoff+timedelta(seconds=2))['reason'],
                             'quote_mode_unverified')
        events = deepcopy(self.events)
        events[-1]['received_at'] = self.opened.isoformat()
        with self.assertRaisesRegex(ValueError, 'receipt_clock_regression'):
            self.model(events)

    def test_missing_minute_is_not_filled_and_old_bar_is_not_current(self):
        missing = self.bar(20)['time']
        events = [e for e in self.events if e.get('bar', {}).get('time') != missing]
        self.assertEqual(self.model(events).snapshot(self.closed)[1], 'warming_up_or_gap')
        self.assertEqual(self.model().snapshot(self.closed+timedelta(minutes=3))[1], 'stale_bar')

    def test_actual_candidate_waits_for_receipt_and_closed_session_never_signals(self):
        events = deepcopy(self.events)
        for event in events:
            if event.get('bar', {}).get('time') == self.bar(30)['time']:
                event['bar'] = self.bar(30, 103.)
        trace = self.model(events)
        before = self.opened+timedelta(minutes=31, seconds=1)
        after = before+timedelta(seconds=1)
        self.assertIsNone(trace.decision(before)['candidate'])
        self.assertEqual(trace.decision(after)['candidate']['direction'], 1)
        self.assertFalse(trace.decision(after)['notify_eligible'])
        self.assertEqual(trace.decision(self.closed)['reason'], 'cash_session_closed')
        self.assertIsNone(trace.decision(self.closed)['candidate'])

    def test_invalid_identity_mode_evidence_and_duplicate_completion_fail_closed(self):
        for case, error in [('identity', 'native_spx'), ('duplicate', 'duplicate_first'),
                            ('mode', 'quote_mode'), ('future', 'completed_before')]:
            events = deepcopy(self.events)
            if case == 'identity': events[0]['symbol'] = 'ES'
            elif case == 'duplicate': events.append(deepcopy(events[-1]))
            elif case == 'mode':
                next(e for e in events if e['kind'] == 'first_completed_observation')['parallel_quote_mode'] = 3
            else:
                event = next(e for e in events if e['kind'] == 'first_completed_observation')
                event['bar']['time'] += 60
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, error):
                self.model(events)

    def test_capture_revisions_are_counted_but_never_substituted_and_output_not_overwritten(self):
        # A real NYSE session is 390 minutes; this 40-minute fixture remains partial.
        for e in self.events:
            if e['kind'] == 'start': e['session_close'] = self.opened.replace(hour=20, minute=0).isoformat()
        self.path.write_text('\n'.join(json.dumps(e) for e in self.events)+'\n')
        raw = dict(contract=dict(symbol='SPX', security_type='IND', exchange='CBOE',
                                 currency='USD', contract_id=416904),
                   received_at='2026-10-23T20:01:00+00:00',
                   rows=[self.bar(i, 103. if i == 30 else 100.) for i in range(40)])
        capture, output = self.root/'capture.json', self.root/'report.json'
        capture.write_text(json.dumps(raw))
        result = diagnose(self.path, capture, output)
        self.assertEqual(result['first_snapshot_differs_from_final'], 1)
        self.assertEqual(result['missing_prospective_minutes'], 350)
        self.assertFalse(result['final_capture_complete'])
        self.assertTrue(all(d['candidate'] is None for d in result['decisions']))
        self.assertFalse(result['signal_quality_evaluated'])
        self.assertFalse(result['notifications_enabled'])
        self.assertFalse(result['holdout'])
        with self.assertRaises(FileExistsError): diagnose(self.path, capture, output)


if __name__ == '__main__':
    unittest.main()
