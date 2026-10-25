import copy, tempfile, unittest
from datetime import timedelta
from spx_daily import schedule, forecast, connect, ingest, issue, create_app

def fixture():
    return [dict(date=str(d.date()),open=5000+i,high=5010+i,low=4990+i,close=5002+i) for i,d in enumerate(schedule('2025-01-01','2025-07-01').index[:100])]
class DailyTests(unittest.TestCase):
    def test_prefix(self):
        rows=fixture(); p=forecast(rows[:90]); rows[-1]['high']=99999
        self.assertEqual(p,forecast(rows[:90]));self.assertIsNone(p['confidence'])
    def test_score_and_immutable(self):
        rows=fixture();db=connect(':memory:');doc=dict(symbol='SPX',security_type='IND',source='IBKR',bars=rows[:90])
        close=schedule(rows[89]['date'],rows[89]['date']).iloc[0].market_close
        ingest(db,doc,close+timedelta(minutes=1));p=issue(db,close+timedelta(minutes=1))
        self.assertEqual(p,issue(db,close+timedelta(minutes=2)))
        doc['bars']=rows[90:91]; nc=schedule(rows[90]['date'],rows[90]['date']).iloc[0].market_close
        ingest(db,doc,nc+timedelta(minutes=1));r=db.execute('SELECT actual_high,high_error FROM predictions').fetchone()
        self.assertEqual(r[0],rows[90]['high']);self.assertAlmostEqual(r[1],p['predicted_high']-r[0])
        doc['bars']=copy.deepcopy(rows[90:91]);doc['bars'][0]['high']+=1
        with self.assertRaises(ValueError):ingest(db,doc,nc+timedelta(minutes=1))
    def test_bad_inputs(self):
        for kind in ('source','gap','future'):
            doc=dict(symbol='SPX',security_type='IND',source='IBKR',bars=fixture())
            if kind=='source':doc['symbol']='ES'
            if kind=='gap':del doc['bars'][4]
            with self.assertRaises(ValueError):ingest(connect(':memory:'),doc,'2025-01-02T12:00:00Z' if kind=='future' else '2026-01-01T00:00:00Z')
    def test_calendar(self):
        self.assertEqual(len(schedule('2026-10-24','2026-10-25')),0)
        self.assertEqual(schedule('2026-11-27','2026-11-27').iloc[0].market_close.hour,18)
    def test_api(self):
        with tempfile.TemporaryDirectory() as d:
            connect(d+'/db').close(); c=create_app(d+'/db').test_client()
            self.assertEqual(c.get('/prediction/tomorrow').status_code,503)
            self.assertEqual(c.get('/').status_code,200)
