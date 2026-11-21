"""Offline tests for the explosion-day risk model (no network, no sklearn needed except the training test)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explosion as X  # noqa: E402
import evaluate_range as E  # noqa: E402

MODEL = json.loads((Path(__file__).resolve().parent/'explosion_model.json').read_text())


def rows(n=25, base=7000.0):
    out, p = [], base
    for i in range(n):
        p *= 1.008 if i % 2 else 0.993          # about 12% annualized realized vol, like a normal market
        out.append((f'2026-10-{i+1:02d}', p-2, p+40, p-40, p))
    return out


class ExplosionTests(unittest.TestCase):
    def test_model_file_is_consistent(self):
        self.assertEqual(MODEL['features'], X.FEATURES)
        self.assertEqual(len(MODEL['coef']), len(X.FEATURES))
        self.assertGreater(MODEL['oos']['n'], 1000)
        self.assertGreater(MODEL['oos']['auc'], 0.55)
        self.assertGreater(MODEL['tiers'][0]['rate'], MODEL['base_rate'])

    def test_features_use_only_prior_sessions_and_the_anchor(self):
        r = rows(); vix = {d: 20.0 for d, *_ in r}
        f1, m = X.features('2026-10-26', r, vix, anchor=r[-1][4]+50)
        f2, _ = X.features('2026-10-26', r, vix, anchor=r[-1][4])
        self.assertAlmostEqual(f1[0], 50/m, places=9)
        self.assertEqual(f2[0], 0.0)
        self.assertEqual(f1[2:], f2[2:])          # only the gap features depend on today

    def test_term_features_use_the_prior_close(self):
        r = rows(); vix = {d: 20.0 for d, *_ in r}
        term = {'vix9d': {d: 22.0 for d, *_ in r}, 'vix3m': {d: 25.0 for d, *_ in r}}
        base, _ = X.features('2026-10-26', r, vix, anchor=r[-1][4])
        f, _ = X.features('2026-10-26', r, vix, anchor=r[-1][4], term=term)
        self.assertEqual(f[:len(base)], base)
        self.assertEqual(len(f), len(X.FEATURES))
        self.assertAlmostEqual(f[-2], 22/20); self.assertAlmostEqual(f[-1], 20/25)
        self.assertTrue(X.uses_term(MODEL))
        del term['vix3m'][r[-1][0]]
        with self.assertRaises(KeyError):          # a missing prior-day close must fail, not silently use stale data
            X.features('2026-10-26', r, vix, anchor=r[-1][4], term=term)

    def test_prob_and_tier(self):
        r = rows(); vix = {d: 20.0 for d, *_ in r}
        term = {'vix9d': {d: 20.0 for d, *_ in r}, 'vix3m': {d: 22.0 for d, *_ in r}}
        f, _ = X.features('2026-10-26', r, vix, anchor=r[-1][4], term=term)
        p = X.prob(MODEL, f)
        self.assertTrue(0 < p < 1)
        self.assertEqual(X.tier(MODEL, 0.0)[0], 'normal')
        self.assertEqual(X.tier(MODEL, 1.0)[0], 'high')

    def test_evening_line_and_record(self):
        call = {'session': '2026-11-19', 'prev_close': 7323.63, 'direction': 'up', 'conf': 89, 'method': 'gap',
                'levels': [{'k': .1, 'high': 7418, 'low': 7395, 'p_high': 85, 'p_low': 80}],
                'range': [7210, 7437], 'explosion': {'tier': 'normal', 'label': 'عادي', 'threshold_pts': 85.0}}
        with tempfile.TemporaryDirectory() as t:
            Path(t, '2026-11-19.json').write_text(json.dumps(call))
            spx = {'2026-11-18': (0, 0, 0, 7323.63), '2026-11-19': (7410, 7415.64, 7193.83, 7210)}
            text = '\n'.join(E.call_lines(t, spx, '2026-11-19'))
        self.assertIn('حركة قوية (≥ 85 نقطة من الافتتاح): حدثت — الخطر الصباحي: عادي', text)
        self.assertIn('الحركة القوية: أيام الخطر 0/0، الأيام العادية 1/1', text)


if __name__ == '__main__':
    unittest.main()
