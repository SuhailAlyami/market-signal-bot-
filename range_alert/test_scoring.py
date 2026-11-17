"""Offline tests: move-from-open lines and TradingAgents shadow scoring (no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_range as D  # noqa: E402
import evaluate_range as E  # noqa: E402


def spy(*closes):
    days = ['2026-11-12', '2026-11-13', '2026-11-16', '2026-11-17', '2026-11-18'][:len(closes)]
    return {d: (c, c, c, c) for d, c in zip(days, closes)}


def records(tmp, **sig):
    for d, s in sig.items():
        Path(tmp, f'{d}.json').write_text(json.dumps({'session': d.replace('_', '-'), 'signal': s}))
    return tmp


class MoveLinesTests(unittest.TestCase):
    def test_points_scale_with_expected_move_and_no_direction_claim(self):
        text = '\n'.join(D.move_lines(92.0))
        self.assertIn('23 نقطة في اتجاه واحد على الأقل: 96%', text)
        self.assertIn('46 نقطة في اتجاه واحد على الأقل: 69%', text)
        self.assertIn('القمة ≥ الافتتاح +9: 85%', text)
        self.assertIn('الاتجاه غير معروف', text)


class DailyCallTests(unittest.TestCase):
    def test_levels_from_previous_close(self):
        lv = D.call_levels(7561.67, 92.0)
        self.assertAlmostEqual(lv['high'], 7561.67+0.174*92, places=6)
        self.assertAlmostEqual(lv['low'], 7561.67-0.11*92, places=6)
        self.assertEqual((round(lv['min_low']), round(lv['max_high'])), (7470, 7654))

    def test_evaluation_flags_for_16_nov(self):
        spx = {'2026-11-13': (7500, 7621.78, 7499.40, 7561.67), '2026-11-16': (7513.98, 7515.60, 7400.15, 7416.59)}
        vix = {'2026-11-13': (0, 0, 0, 19.3), '2026-11-16': (0, 0, 0, 22.0)}
        e = E.evaluate(spx, vix, '2026-11-16')
        self.assertFalse(e['up']); self.assertFalse(e['hit_high']); self.assertTrue(e['hit_low']); self.assertFalse(e['in1'])


class ShadowScoringTests(unittest.TestCase):
    def test_no_records_dir_gives_nothing(self):
        self.assertEqual(E.shadow_lines(None, spy(100, 101), '2026-11-13'), [])
        self.assertEqual(E.shadow_lines('/nonexistent', spy(100, 101), '2026-11-13'), [])

    def test_hold_is_no_position_and_baseline_is_always_long(self):
        with tempfile.TemporaryDirectory() as t:
            out = E.shadow_lines(records(t, **{'2026_11_16': 'Hold'}), spy(100, 100, 98), '2026-11-16')
        text = '\n'.join(out)
        self.assertIn('بلا مركز', text)
        self.assertIn('-2.00%', text)          # SPY move and always-long baseline
        self.assertIn('قرارات اتجاه 0، صحيحة 0', text)
        self.assertIn('اتباعه +0.00%', text)

    def test_direction_hits_and_cumulative_pnl(self):
        with tempfile.TemporaryDirectory() as t:
            records(t, **{'2026_11_16': 'Sell', '2026_11_17': 'Buy', '2026_11_18': 'Buy'})
            out = E.shadow_lines(t, spy(100, 100, 98, 99, 99.5), '2026-11-17')   # 11-18 is after `day`: excluded
        text = '\n'.join(out)
        self.assertIn('✅ صحيح', text)          # Buy on 11-17, SPY +1.02%
        self.assertIn('التراكمي (2 جلسة)', text)
        self.assertIn('قرارات اتجاه 2، صحيحة 2', text)

    def test_wrong_call_marked(self):
        with tempfile.TemporaryDirectory() as t:
            out = E.shadow_lines(records(t, **{'2026_11_16': 'Buy'}), spy(100, 100, 98), '2026-11-16')
        self.assertIn('❌ خطأ', '\n'.join(out))


if __name__ == '__main__':
    unittest.main()
