import unittest
from datetime import datetime, timedelta
from pathlib import Path

from run import aggregate5, atr_before, coverage, detect, match_legs, reference_legs, score
from objective_review import Bar, NY, load_sessions


def bars(prices):
    start = datetime(2026,11,6,9,30,tzinfo=NY)
    return [Bar(start+timedelta(minutes=5*i),p,p+.5,p-.5,p) for i,p in enumerate(prices)]


class WaveCaptureTests(unittest.TestCase):
    def test_atr_excludes_decision_bar(self):
        source = bars([100]*6+[1000])
        self.assertEqual(atr_before(source,6),1)
        self.assertIsNone(atr_before(source,5))

    def test_closed_bar_decision_and_price_mirror(self):
        source = bars([100]*7+[106,112,110,105,99,94,90,85])
        first = detect(source)[0]
        self.assertEqual(first['index'],7)
        self.assertEqual(first['decision'],source[7].at+timedelta(minutes=5))
        mirror = [Bar(b.at,200-b.open,200-b.low,200-b.high,200-b.close) for b in source]
        self.assertEqual([(s['index'],s['side']) for s in detect(mirror)],
                         [(s['index'],-s['side']) for s in detect(source)])

    def test_cooldown_updates_state_without_delayed_reemit(self):
        source = bars([100]*7+[106,95,110,111,112,113,114,115,116])
        self.assertEqual([r['index'] for r in detect(source)],[7])

    def test_hindsight_legs_and_terminal_leg_explicit(self):
        source = bars([100,105,110,120,130,115,100])
        legs = reference_legs(source)
        self.assertEqual([(l['start'],l['end'],l['side'],l['terminal']) for l in legs],
                         [(0,4,1,False),(4,6,-1,True)])

    def test_coverage_uses_each_signal_once_and_correct_close_time(self):
        source = bars([100,105,110,120,130,115,100])
        signal = dict(index=1,side=1)
        leg = reference_legs(source)[0]
        result = match_legs(source,[signal],[leg,leg])
        self.assertTrue(result[0]['early'])
        self.assertFalse(result[1]['matched'])
        self.assertEqual(result[0]['lag_minutes'],5)
        self.assertEqual(result[0]['start_Riyadh'],'2026-11-06T17:35:00+03:00')

    def test_fill_after_latency_and_session_censor(self):
        source = bars([100+i*.1 for i in range(78)])
        signal = dict(decision=source[10].at+timedelta(minutes=5),side=1,r=5)
        result = score(source,5,source[-1].at+timedelta(minutes=5),signal,1,15)
        self.assertEqual(result['entry'],source[14].open)
        signal['decision']=source[-2].at
        self.assertEqual(score(source,5,source[-1].at+timedelta(minutes=5),signal,1,0)['status'],
                         'INSUFFICIENT_SAME_SESSION_HORIZON')

    def test_uniform_aggregation_preserves_first_last_prices(self):
        start = datetime(2026,11,6,9,30,tzinfo=NY)
        raw = [Bar(start+timedelta(minutes=i),100+i,101+i,99+i,100+i) for i in range(10)]
        result = aggregate5(raw,1)
        self.assertEqual((len(result),result[0].open,result[0].close,result[-1].close),(2,100,104,109))
        with self.assertRaises(ValueError):
            aggregate5(raw[:-1],1)

    def test_market_prefix_stability(self):
        path = Path(__file__).resolve().parents[1]/'opening_validation_raw.json.gz'
        sessions,_ = load_sessions(path)
        for index in (0,58,115):
            _,raw,_,step,_ = sessions[index]
            source = aggregate5(raw,step)
            full = detect(source)
            for n in (20,40,60):
                self.assertEqual(detect(source[:n]),[r for r in full if r['index']<n])


if __name__ == '__main__':
    unittest.main()
