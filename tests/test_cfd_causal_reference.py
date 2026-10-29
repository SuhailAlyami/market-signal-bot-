import random
import unittest
from cfd_causal_reference import Bar, Watch, directions, replay


def fixtures(n=180):
    rng = random.Random(412)
    bars, price = [], 100.0
    for i in range(n):
        close = price+rng.uniform(-.3, .3)
        bars.append(Bar(i*60000, price, max(price, close)+.2,
                        min(price, close)-.2, close))
        price = close
    return bars


class CausalTests(unittest.TestCase):
    def test_prefix_replay(self):
        bars = fixtures()
        for model in (0, 1):
            full = replay(bars, model)
            for end in (31, 50, 90, 150):
                self.assertEqual(replay(bars[:end], model), full[:end])

    def test_future_poison(self):
        bars = fixtures()
        poison = [Bar(b.time, b.open*100, b.high*100, b.low*100, b.close*100)
                  for b in bars[90:]]
        for model in (0, 1):
            self.assertEqual(replay(bars, model)[:90], replay(bars[:90]+poison, model)[:90])

    def test_known_ready_up(self):
        bars = [Bar(i*60000, 100, 100.5, 99.5, 100) for i in range(30)]
        bars.append(Bar(30*60000, 100, 100.5, 99.8, 100.4))
        self.assertEqual(directions(bars), (True, 1, 0))

    def test_failed_break_nonempty_replay(self):
        bars = [Bar(i*60000, 100, 100.5, 99.5, 100) for i in range(90)]
        bars[35] = Bar(35*60000, 99.7, 100.3, 99.4, 100.2)
        self.assertEqual(directions(bars[:36]), (True, 0, 1))
        prefix = replay(bars[:36], 1)
        self.assertEqual(prefix[-1][3], 'UP')
        self.assertEqual(replay(bars, 1)[:36], prefix)
        poisoned = bars[:36]+[Bar(b.time, 110, 112, 109, 111) for b in bars[36:]]
        self.assertEqual(replay(poisoned, 1)[:36], prefix)

    def test_mirror_symmetry(self):
        bars = fixtures()
        mirrored = [Bar(b.time, 200-b.open, 200-b.low, 200-b.high, 200-b.close) for b in bars]
        for i in range(31, len(bars)):
            v, a, b = directions(bars[:i])
            self.assertEqual(directions(mirrored[:i]), (v, -a, -b))

    def test_invalid_and_gap_reject_features(self):
        bars = fixtures(31)
        b = bars[-1]
        for bad in (Bar(b.time+60000,b.open,b.high,b.low,b.close),
                    Bar(b.time,b.open,b.low,b.high,b.close),
                    Bar(b.time,b.open,b.high,b.low,float('nan'))):
            self.assertEqual(directions(bars[:-1]+[bad]), (False, 0, 0))

    def test_partial_bar_cannot_change_state(self):
        state = Watch()
        self.assertIsNone(state.step(Bar(0,100,101,99,100), True, 1, confirmed=False))
        self.assertEqual(vars(state), vars(Watch()))

    def test_gap_cancels_without_same_bar_rearm(self):
        state = Watch()
        self.assertEqual(state.step(Bar(0,100,101,99,100),True,1),'UP')
        self.assertEqual(state.step(Bar(900000,100,101,99,100),True,1),'END')
        self.assertEqual(state.side,0)

    def test_close_invalidation_and_cooldown(self):
        for sign in (1,-1):
            state = Watch()
            state.step(Bar(0,100,101,99,100),True,sign)
            invalid_close = 99 if sign == 1 else 101
            self.assertEqual(state.step(Bar(60000,100,101,99,invalid_close),True,sign),'END')
            self.assertIsNone(state.step(Bar(120000,100,101,99,100),True,sign))

    def test_ten_minute_expiry(self):
        state=Watch()
        state.step(Bar(0,100,101,99,100),True,1)
        for i in range(1,10):
            self.assertIsNone(state.step(Bar(i*60000,100,101,99,100),True,1))
        self.assertEqual(state.step(Bar(600000,100,101,99,100),True,1),'END')
        self.assertEqual(state.step(Bar(660000,100,101,99,100),True,1),'UP')


if __name__ == '__main__':
    unittest.main()
