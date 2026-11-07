import unittest
from datetime import datetime,timedelta

from protect import protected_score
from objective_review import Bar,NY


class ProtectionTests(unittest.TestCase):
    def run_case(self,quotes,step=5,side=1):
        at = datetime(2026,11,6,10,tzinfo=NY)
        raw = [Bar(at+timedelta(minutes=step*i),*q) for i,q in enumerate(quotes)]
        signal = dict(decision=at,side=side,r=5)
        return protected_score(raw,step,at+timedelta(minutes=30),signal,0)

    def test_arm_not_retroactive_within_same_bar(self):
        q = [(100,106,99,105)]+[(105,108,104,107)]*5
        result = self.run_case(q)
        self.assertEqual(result['gross_low'],7)
        self.assertEqual(result['protection_armed_Riyadh'],'2026-11-06T18:05:00+03:00')

    def test_next_bar_protected_stop_and_cost_is_still_payable(self):
        q = [(100,106,99,105),(103,104,99,101)]+[(101,104,100,103)]*4
        result = self.run_case(q)
        self.assertEqual((result['gross_low'],result['exit']),(0,'protected_stop'))
        self.assertEqual(result['gross_low']-1,-1)

    def test_favorable_touch_without_close_does_not_arm(self):
        q = [(100,106,99,102)]+[(102,104,101,103)]*5
        result = self.run_case(q)
        self.assertIsNone(result['protection_armed_Riyadh'])

    def test_gap_below_entry_is_not_free_break_even(self):
        q = [(100,106,99,105),(98,99,97,98)]+[(98,100,97,99)]*4
        result = self.run_case(q)
        self.assertEqual((result['gross_low'],result['exit']),(-2,'protected_stop_gap'))

    def test_initial_stop_target_ambiguity_is_bounded(self):
        result = self.run_case([(100,111,94,105)]+[(105,108,104,107)]*5)
        self.assertEqual((result['gross_low'],result['gross_high']),(-5,10))
        self.assertIsNone(result['protection_armed_Riyadh'])

    def test_armed_stop_target_ambiguity_is_bounded(self):
        result = self.run_case([(100,106,99,105),(105,111,99,106)]+[(106,108,104,107)]*4)
        self.assertEqual((result['gross_low'],result['gross_high']),(0,10))

    def test_one_minute_feed_still_waits_for_five_minute_close(self):
        q = [(100,107,100,106),(106,107,99,101)]+[(101,108,101,106)]*28
        result = self.run_case(q,step=1)
        self.assertEqual(result['gross_low'],6)
        self.assertEqual(result['protection_armed_Riyadh'],'2026-11-06T18:05:00+03:00')

    def test_price_mirror_preserves_pnl(self):
        q = [(100,106,99,105),(103,104,99,101)]+[(101,104,100,103)]*4
        opposite = [(200-o,200-l,200-h,200-c) for o,h,l,c in q]
        self.assertEqual(self.run_case(q)['gross_low'],self.run_case(opposite,side=-1)['gross_low'])


if __name__=='__main__':
    unittest.main()
