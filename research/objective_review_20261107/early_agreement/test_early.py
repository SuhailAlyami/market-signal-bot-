import gzip
import json
import unittest
from datetime import datetime,timedelta
from pathlib import Path

from run_early import fast_events,paired_change
from objective_review import Bar,NY,load_sessions
from ensemble_audit.audit import combine
from wave_capture.run import aggregate5


def fixture(prices):
    start = datetime(2026,11,6,9,30,tzinfo=NY)
    return [Bar(start+timedelta(minutes=5*i),prices[i-1] if i else p,
                max(prices[i-1] if i else p,p)+.5, min(prices[i-1] if i else p,p)-.5,p)
            for i,p in enumerate(prices)]


class EarlyAgreementTests(unittest.TestCase):
    def test_fixed_thirty_minute_range_and_closed_confirmation(self):
        bars = fixture([100]*6+[102,100,103])
        levels = [e for e in fast_events(bars) if e['method']!='wave']
        self.assertEqual([(e['method'],e['index'],e['side']) for e in levels],[('breakout',6,1),('reclaim',7,-1)])
        self.assertEqual(levels[0]['decision'],bars[6].at+timedelta(minutes=5))

    def test_each_method_first_event_only(self):
        levels = [e for e in fast_events(fixture([100]*6+[102,100,98,100,104,100])) if e['method']!='wave']
        self.assertEqual(len(levels),2)
        self.assertEqual(levels[0]['side'],1)

    def test_no_partial_range_and_equal_edge_not_a_break(self):
        self.assertEqual(fast_events(fixture([100]*6)),[])
        self.assertEqual([e for e in fast_events(fixture([100]*6+[100.5])) if e['method']!='wave'],[])

    def test_price_mirror_preserves_times_and_flips_sides(self):
        bars = fixture([100]*6+[102,100,98,100,104,100])
        mirror = [Bar(b.at,200-b.open,200-b.low,200-b.high,200-b.close) for b in bars]
        self.assertEqual([(e['index'],e['method'],e['side']) for e in fast_events(mirror)],
                         [(e['index'],e['method'],-e['side']) for e in fast_events(bars)])

    def test_paired_net_counts_new_and_removed_trades_with_costs(self):
        rows = [dict(day='a',variant='fast5',delay=0,outcome=dict(status='SCORED',gross_low=5)),
                dict(day='b',variant='control15',delay=0,outcome=dict(status='SCORED',gross_low=2))]
        self.assertEqual(paired_change(rows,['a','b'])['fast_minus_control_cost1'],3)

    def test_market_prefix_stability(self):
        root = Path(__file__).resolve().parents[1]
        sessions,_ = load_sessions(root/'opening_validation_raw.json.gz')
        for day_index in (0,58,115):
            _,raw,_,step,_ = sessions[day_index]
            bars = aggregate5(raw,step)
            full = combine(fast_events(bars),True)
            for n in (12,24,48):
                self.assertEqual(combine(fast_events(bars[:n]),True),[e for e in full if e['index']<n])

    def test_control_matches_previous_agreement_exactly(self):
        root = Path(__file__).resolve().parents[1]
        path = root/'early_agreement/results.json.gz'
        if not path.exists():
            self.skipTest('Generate integration results first')
        current = json.loads(gzip.decompress(path.read_bytes()))
        prior = json.loads(gzip.decompress((root/'ensemble_audit/results.json.gz').read_bytes()))
        for group in ('older','recent','all'):
            for metric in ('execution','coverage'):
                self.assertEqual(current['report'][group]['variants']['control15'][metric],
                                 prior['report'][group]['methods']['consensus'][metric])


if __name__=='__main__':
    unittest.main()
