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


if __name__ == '__main__':
    unittest.main()
