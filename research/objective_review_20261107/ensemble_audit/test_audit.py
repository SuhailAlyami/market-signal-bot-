import unittest
import gzip
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from audit import bootstrap_difference,combine,complementarity,constituent_events
from objective_review import load_sessions
from wave_capture.run import aggregate5


def event(minute,method,side):
    return dict(decision=datetime(2026,11,6,15,tzinfo=timezone.utc)+timedelta(minutes=minute),
                method=method,side=side,index=minute//5,r=5)


class EnsembleTests(unittest.TestCase):
    def test_simultaneous_conflict_skips_union_independent_of_input_order(self):
        events = [event(0,'wave',1),event(0,'breakout',-1)]
        self.assertEqual(combine(events),[])
        self.assertEqual(combine(events[::-1]),[])

    def test_consensus_requires_two_distinct_methods(self):
        events = [event(0,'wave',1),event(5,'wave',1)]
        self.assertEqual(combine(events,True),[])
        with self.assertRaises(ValueError):
            combine([events[0],events[0]],True)

    def test_vote_expiration_boundary(self):
        self.assertEqual(len(combine([event(0,'wave',1),event(15,'reclaim',1)],True)),1)
        self.assertEqual(combine([event(0,'wave',1),event(20,'reclaim',1)],True),[])

    def test_simultaneous_consensus_order_and_support(self):
        events = [event(0,'wave',1),event(0,'breakout',1),event(0,'reclaim',-1)]
        self.assertEqual(combine(events,True)[0]['support'],['breakout','wave'])
        self.assertEqual(combine(events,True),combine(events[::-1],True))

    def test_old_majority_not_reissued_on_new_opposite_event(self):
        events = [event(0,'wave',1),event(0,'breakout',1),event(10,'reclaim',-1)]
        self.assertEqual(len(combine(events,True)),1)

    def test_cooldown_and_prefix_invariance(self):
        events = [event(0,'wave',1),event(10,'breakout',1),event(30,'reclaim',-1)]
        self.assertEqual([e['index'] for e in combine(events)],[0,6])
        full = combine(events)
        self.assertEqual(combine(events[:2]),[e for e in full if e['index']<6])

    def test_complementarity_counts_leg_identity_once(self):
        a = dict(day='2026-11-06',start=1,end=3,matched=True,early=True)
        b = dict(day='2026-11-06',start=4,end=7,matched=True,early=False)
        matrix = [dict(a,method='a'),dict(a,method='b'),dict(b,method='b')]
        result = complementarity(matrix,('a','b'))
        self.assertEqual(result['matched']['raw_union_ceiling'],2)
        self.assertEqual(result['matched']['unique_by_method'],{'a':0,'b':1})
        self.assertEqual(result['early']['raw_union_ceiling'],1)

    def test_paired_bootstrap_includes_inactive_days_and_costs_cancel(self):
        rows = [dict(day='a',candidate=dict(status='SCORED',gross_low=4),up=dict(status='SCORED',gross_low=1))]
        result = bootstrap_difference(rows,['a','b'])
        self.assertEqual(result['candidate_minus_always_up_cost1'],3)
        self.assertEqual(result['paired_session_bootstrap_95'],[0,6])

    def test_market_ensemble_prefix_invariance(self):
        root = Path(__file__).resolve().parents[1]
        sessions,_ = load_sessions(root/'opening_validation_raw.json.gz')
        for day_index in (0,58,115):
            _,raw,bars15,step,_ = sessions[day_index]
            bars5 = aggregate5(raw,step)
            full = constituent_events(bars5,bars15)
            for n in (20,40,60):
                end = bars5[n-1].at+timedelta(minutes=5)
                prefix = constituent_events(bars5[:n],[b for b in bars15 if b.at+timedelta(minutes=15)<=end])
                for mode in (False,True):
                    self.assertEqual(combine(prefix,mode),[e for e in combine(full,mode) if e['decision']<=end])

    def test_wave_control_exactly_reproduced_when_results_exist(self):
        root = Path(__file__).resolve().parents[1]
        current = root/'ensemble_audit/results.json.gz'
        if not current.exists():
            self.skipTest('Run audit.py to generate the integration result first')
        prior = json.loads(gzip.decompress((root/'wave_capture/results.json.gz').read_bytes()))
        result = json.loads(gzip.decompress(current.read_bytes()))
        for group in ('older','recent','all'):
            self.assertEqual(prior['report'][group]['coverage'],result['report'][group]['methods']['wave']['coverage'])
            self.assertEqual(prior['report'][group]['execution'],result['report'][group]['methods']['wave']['execution'])


if __name__=='__main__':
    unittest.main()
