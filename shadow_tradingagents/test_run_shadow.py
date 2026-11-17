"""Offline tests for model selection of the shadow runner (no network, no TradingAgents import)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_shadow as R  # noqa: E402


class ModelPlanTests(unittest.TestCase):
    def test_unreliable_tool_caller_not_preferred(self):
        self.assertNotIn('llama-3.1-8b-instant', R.QUICK_PREF)

    def test_candidates_respect_availability_and_override(self):
        avail = ['llama-3.3-70b-versatile', 'openai/gpt-oss-20b']
        self.assertEqual(R.candidates(R.QUICK_PREF, avail, None), ['llama-3.3-70b-versatile', 'openai/gpt-oss-20b'])
        self.assertEqual(R.candidates(R.QUICK_PREF, avail, 'x/y'), ['x/y'])
        with self.assertRaises(RuntimeError):
            R.candidates(R.QUICK_PREF, ['whisper-large-v3'], None)

    def test_ranked_by_probed_tpm_and_unusable_dropped(self):
        avail = ['llama-3.3-70b-versatile', 'openai/gpt-oss-20b', 'meta-llama/llama-4-scout-17b-16e-instruct', 'qwen/qwen3-32b']
        tpm = {'llama-3.3-70b-versatile': 12000, 'openai/gpt-oss-20b': 8000,
               'meta-llama/llama-4-scout-17b-16e-instruct': 30000, 'qwen/qwen3-32b': 0}
        self.assertEqual(R.candidates(R.QUICK_PREF, avail, None, tpm),
                         ['meta-llama/llama-4-scout-17b-16e-instruct', 'llama-3.3-70b-versatile', 'openai/gpt-oss-20b'])
        # below MIN_TPM still kept as a last resort, never first
        self.assertEqual(R.candidates(R.QUICK_PREF, ['openai/gpt-oss-20b'], None, {'openai/gpt-oss-20b': 8000}), ['openai/gpt-oss-20b'])
        with self.assertRaises(RuntimeError):
            R.candidates(R.QUICK_PREF, avail, None, {m: 0 for m in avail})

    def test_plan_rotates_quick_model_and_is_bounded(self):
        pairs = R.plan(['D1', 'D2'], ['Q1', 'Q2', 'Q3'])
        self.assertEqual(pairs, [('D1', 'Q1'), ('D1', 'Q2'), ('D1', 'Q3')])
        self.assertEqual(R.plan(['D1', 'D2'], ['Q1']), [('D1', 'Q1'), ('D2', 'Q1')])
        self.assertEqual(R.plan(['D1'], ['Q1']), [('D1', 'Q1')])


class PacingTests(unittest.TestCase):
    def make(self):
        t = {'now': 0.0}
        slept = []
        def sleep(x): slept.append(x); t['now'] += x
        class Fake:
            model = 'm'
            calls = 0
            fail = 0
            def invoke(self, input, config=None, **kw):
                Fake.calls += 1
                if Fake.fail:
                    Fake.fail -= 1
                    raise RuntimeError('429 RESOURCE_EXHAUSTED')
                return 'ok'
        R.pace_invoke(Fake, interval=13, wait_on_limit=65, tries=3, sleep=sleep, clock=lambda: t['now'])
        return Fake, slept

    def test_calls_spaced_per_model(self):
        Fake, slept = self.make()
        f = Fake()
        self.assertEqual([f.invoke('a'), f.invoke('b'), f.invoke('c')], ['ok', 'ok', 'ok'])
        self.assertEqual(slept, [13, 13])

    def test_rate_limit_waits_and_retries_then_gives_up(self):
        Fake, slept = self.make()
        Fake.fail = 1
        self.assertEqual(Fake().invoke('a'), 'ok')
        self.assertIn(65, slept)
        Fake.fail = 5
        with self.assertRaises(RuntimeError):
            Fake().invoke('b')

    def test_google_models_split_and_no_retired_models(self):
        self.assertFalse(set(R.GOOGLE_DEEP) & set(R.GOOGLE_QUICK[:2]))
        self.assertFalse([m for m in R.GOOGLE_DEEP + R.GOOGLE_QUICK if m.startswith('gemini-2.5')])


if __name__ == '__main__':
    unittest.main()
