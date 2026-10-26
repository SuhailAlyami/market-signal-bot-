import json
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from spx_price_runtime import SPXPriceRuntime
from test_spx_price_watch import frame


class CandidateDispositionTests(unittest.TestCase):
    def test_candidate_active_suppression_and_dedupe_are_explained(self):
        data = frame()
        data.iloc[30] = [100, 100.1, 98.9, 99]
        data.iloc[31] = [99, 99.1, 98.7, 98.8]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            journal = path/'journal.jsonl'
            runtime = SPXPriceRuntime(path/'state.json', journal)
            states = []
            for i in (30, 31):
                end = data.index[i].to_pydatetime()+timedelta(minutes=1)
                states.append([e['state'] for e in runtime._process_bar('SPX', data, i, end)])
            self.assertEqual(states, [['SETUP'], []])
            records = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
            records = [r for r in records if r['record_type']=='candidate_disposition']
            self.assertEqual([r['reason'] for r in records], ['setup_created', 'active_setup'])
            self.assertTrue(all(r['candidate'] is not None and not r['notify_eligible'] for r in records))
            before = journal.read_bytes()
            self.assertEqual(runtime._process_bar('SPX', data, 31, end), [])
            self.assertEqual(journal.read_bytes(), before)

    def test_no_candidate_and_cooldown_are_distinct_without_enabling_delivery(self):
        data = frame()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            runtime = SPXPriceRuntime(path/'state.json', path/'journal.jsonl')
            end = data.index[30].to_pydatetime()+timedelta(minutes=1)
            self.assertEqual(runtime._process_bar('SPX', data, 30, end), [])
            data.iloc[31] = [100, 100.1, 98.9, 99]
            runtime.state['symbols']['SPX']['cooldown_until'] = (end+timedelta(minutes=5)).isoformat()
            self.assertEqual(runtime._process_bar('SPX', data, 31, end+timedelta(minutes=1)), [])
            records = [json.loads(line) for line in (path/'journal.jsonl').read_text(encoding='utf-8').splitlines()]
            records = [r for r in records if r['record_type']=='candidate_disposition']
            self.assertEqual([r['reason'] for r in records], ['no_candidate', 'cooldown'])
            self.assertTrue(all(r['delivery_blocker']=='research_notifications_disabled' for r in records))
