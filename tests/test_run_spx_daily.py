from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from run_spx_daily import cycle, source_window
from spx_daily import schedule


class FakeCollector:
    def __init__(self, mode='valid'):self.calls=0;self.mode=mode
    def __call__(self,start,end,directory,now=None):
        self.calls+=1
        directory=Path(directory);directory.mkdir(parents=True)
        if self.mode=='failed':return dict(status='WAIT_VALID_DATA',data_complete=False)
        rows=[]
        for day in schedule(start,end).index:
            price=5000+(day.date().toordinal()%1000)/10
            rows.append(dict(date=str(day.date()),open=price,high=price+10,low=price-10,close=price+2))
        raw=b'original provider evidence'
        (directory/'raw.json').write_bytes(raw)
        raw_sha=hashlib.sha256(raw).hexdigest()
        doc=dict(source='IBKR',symbol='SPX',security_type='IND',bars=rows,raw_sha256=raw_sha)
        encoded=json.dumps(doc).encode()
        (directory/'input.json').write_bytes(encoded)
        manifest=dict(data_complete=True,start=start,end=end,raw_sha256=raw_sha,input_sha256=hashlib.sha256(encoded).hexdigest())
        (directory/'manifest.json').write_text(json.dumps(manifest))
        if self.mode=='tampered':(directory/'input.json').write_bytes(encoded+b' ')
        return dict(status='VALIDATED_HISTORY_NOT_PREDICTIVE_PROOF',data_complete=True)


class DailyRunnerTests(unittest.TestCase):
    def test_concurrent_cycles_reserve_before_acquisition(self):
        started=threading.Event();release=threading.Event();fake=FakeCollector('failed')
        def blocked(*args,**kwargs):
            started.set()
            if not release.wait(5):raise RuntimeError('test timeout')
            return fake(*args,**kwargs)
        with tempfile.TemporaryDirectory() as root, ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(cycle,root,'2026-10-26T20:06Z',blocked)
            try:
                self.assertTrue(started.wait(5))
                second=cycle(root,'2026-10-26T20:07Z',fake)
                self.assertEqual(second['status'],'ALREADY_ATTEMPTED')
                self.assertEqual(second['previous_status'],'RUNNING')
            finally:release.set()
            self.assertEqual(first.result(timeout=5)['status'],'WAIT_VALID_DATA')
            self.assertEqual(fake.calls,1)

    def test_close_grace_early_close_and_dst(self):
        self.assertEqual(source_window('2026-10-26T20:04Z')[1],'2026-10-23')
        self.assertEqual(source_window('2026-10-26T20:05Z')[1],'2026-10-26')
        self.assertEqual(source_window('2026-11-27T18:04Z')[1],'2026-11-25')
        self.assertEqual(source_window('2026-11-27T18:05Z')[1],'2026-11-27')
        self.assertEqual(source_window('2026-11-02T20:59Z')[1],'2026-10-30')
        with self.assertRaises(ValueError):source_window('2026-10-26T20:05')

    def test_restart_dedup_and_next_session_scoring(self):
        fake=FakeCollector()
        with tempfile.TemporaryDirectory() as root:
            first=cycle(root,'2026-10-26T20:06Z',fake)
            self.assertEqual(first['status'],'RESEARCH_FORECAST_ISSUED')
            self.assertEqual(first['prediction']['date'],'2026-10-27')
            repeated=cycle(root,'2026-10-26T20:07Z',fake)
            self.assertEqual(repeated['status'],'ALREADY_ATTEMPTED')
            self.assertEqual(fake.calls,1)
            second=cycle(root,'2026-10-27T20:06Z',fake)
            self.assertEqual(second['prediction']['date'],'2026-10-28')
            with closing(sqlite3.connect(Path(root)/'spx-daily.sqlite')) as db:
                row=db.execute("SELECT payload,actual_high,direction_accuracy FROM predictions WHERE date='2026-10-27'").fetchone()
            self.assertEqual(json.loads(row[0]),first['prediction'])
            self.assertIsNotNone(row[1]);self.assertIn(row[2],(0,1))

    def test_invalid_capture_is_not_retried_or_learned(self):
        for mode in ('failed','tampered'):
            fake=FakeCollector(mode)
            with tempfile.TemporaryDirectory() as root:
                report=cycle(root,'2026-10-26T20:06Z',fake)
                self.assertEqual(report['status'],'WAIT_VALID_DATA')
                self.assertFalse((Path(root)/'spx-daily.sqlite').exists())
                cycle(root,'2026-10-26T20:10Z',fake)
                self.assertEqual(fake.calls,1)

    def test_late_source_scores_without_backdated_forecast(self):
        with tempfile.TemporaryDirectory() as root:
            report=cycle(root,'2026-10-27T15:00Z',FakeCollector())
            self.assertEqual(report['status'],'SCORED_NO_NEW_PREDICTION')
            with closing(sqlite3.connect(Path(root)/'spx-daily.sqlite')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM predictions').fetchone()[0],0)

    def test_crashed_reservation_never_duplicates_request(self):
        fake=FakeCollector('failed')
        with tempfile.TemporaryDirectory() as root:
            cycle(root,'2026-10-26T20:06Z',fake)
            with closing(sqlite3.connect(Path(root)/'runs.sqlite')) as state:
                with state:state.execute("UPDATE runs SET status='RUNNING',payload=NULL")
            report=cycle(root,'2026-10-26T20:09Z',fake)
            self.assertEqual(report['previous_status'],'RUNNING')
            self.assertEqual(fake.calls,1)
