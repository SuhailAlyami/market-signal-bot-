import unittest
from cfd_causal_reference import Bar, directions
from cfd_acceleration_v4 import acceleration, AccelerationWatch


def sample():
    bars=[Bar(i*60000,100,100.5,99.5,100) for i in range(30)]
    bars.append(Bar(1800000,100,102,99.9,101.9))
    return bars


class AccelerationTests(unittest.TestCase):
    def test_impulse_rejected_by_old_range_detected_by_new(self):
        bars=sample()
        self.assertEqual(directions(bars)[1],0)
        self.assertEqual(acceleration(bars),1)

    def test_down_symmetry(self):
        mirrored=[Bar(b.time,200-b.open,200-b.low,200-b.high,200-b.close) for b in sample()]
        self.assertEqual(acceleration(mirrored),-1)

    def test_upper_wick_rejected(self):
        bars=sample()
        bars[-1]=Bar(1800000,100,103,99.9,100.6)
        self.assertEqual(acceleration(bars),0)

    def test_gap_rejected(self):
        bars=sample()
        b=bars[-1]
        bars[-1]=Bar(b.time+60000,b.open,b.high,b.low,b.close)
        self.assertEqual(acceleration(bars),0)

    def test_future_does_not_change_prefix(self):
        bars=sample()
        before=[acceleration(bars[:i]) for i in range(1,len(bars)+1)]
        future=bars+[Bar(1860000,1000,1200,900,1100)]
        self.assertEqual(before,[acceleration(future[:i]) for i in range(1,len(bars)+1)])

    def test_independent_watch_and_partial(self):
        state=AccelerationWatch()
        b=sample()[-1]
        self.assertIsNone(state.step(b,True,1,False))
        self.assertEqual(state.step(b,True,1),'UP')
        self.assertIsNone(state.step(Bar(1860000,102,103,101,102),True,1))

    def test_expiry_and_no_same_bar_rearm(self):
        state=AccelerationWatch()
        for i in range(11):
            e=state.step(Bar(i*60000,100,101,99,100),True,1)
        self.assertEqual(e,'END')
        self.assertEqual(state.side,0)

    def test_confirmed_opposite_impulse_can_flip_after_invalidation(self):
        state=AccelerationWatch()
        state.step(Bar(0,100,101,99,100),True,-1)
        self.assertEqual(state.step(Bar(60000,100,103,99.9,102.9),True,1),'UP')
        self.assertEqual(state.side,1)

    def test_gap_cannot_flip(self):
        state=AccelerationWatch()
        state.step(Bar(0,100,101,99,100),True,-1)
        self.assertEqual(state.step(Bar(120000,100,103,99.9,102.9),True,1),'END')
