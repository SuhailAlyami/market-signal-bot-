import io
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import llm_chain as C

NO_KEYS = {'GEMINI_API_KEY': '', 'GOOGLE_API_KEY': '', 'GROQ_API_KEY': '', 'OPENROUTER_API_KEY': '',
           'GEMINI_MODELS': '', 'GROQ_MODELS': '', 'OPENROUTER_MODELS': ''}


def keys(**kw):
    return mock.patch.dict(os.environ, {**NO_KEYS, **kw})


class ChainTests(unittest.TestCase):
    def test_no_keys_fails_with_clear_message(self):
        with keys():
            with self.assertRaises(RuntimeError) as e:
                C.run('p', 'c', sleep=lambda s: None)
        self.assertIn('no provider key', str(e.exception))

    def test_gemini_limit_falls_through_to_groq(self):
        def fake(url, body=None, headers=None):
            if 'generativelanguage' in url:
                raise C.Skip('HTTP 429: quota')
            return {'choices': [{'message': {'content': 'تقرير'}}]}
        with keys(GEMINI_API_KEY='g', GROQ_API_KEY='q', GEMINI_MODELS='gm1,gm2', GROQ_MODELS='llama'):
            with mock.patch.object(C, 'http_json', side_effect=fake) as h:
                self.assertEqual(C.run('p', 'c', sleep=lambda s: None), ('groq', 'llama', 'تقرير'))
        self.assertEqual(h.call_count, 3)   # two Gemini models tried, then Groq answered

    def test_openrouter_uses_only_zero_priced_models(self):
        listing = {'data': [
            {'id': 'paid/big', 'pricing': {'prompt': '0.000001', 'completion': '0.000002'}, 'context_length': 999999},
            {'id': 'free/small', 'pricing': {'prompt': '0', 'completion': '0'}, 'context_length': 8000},
            {'id': 'free/large', 'pricing': {'prompt': '0', 'completion': '0'}, 'context_length': 128000}]}
        with keys(OPENROUTER_API_KEY='o'):
            with mock.patch.object(C, 'http_json', return_value=listing):
                self.assertEqual(C.openrouter_models(), ['free/large', 'free/small'])

    def test_empty_reply_moves_on(self):
        replies = iter([{'choices': [{'message': {'content': '  '}}]}, {'choices': [{'message': {'content': 'ok'}}]}])
        with keys(GROQ_API_KEY='q', GROQ_MODELS='a,b'):
            with mock.patch.object(C, 'http_json', side_effect=lambda *a, **k: next(replies)):
                self.assertEqual(C.run('p', 'c', sleep=lambda s: None), ('groq', 'b', 'ok'))

    def test_context_cut_to_provider_budget(self):
        seen = []

        def fake(url, body=None, headers=None):
            seen.append(len(body['messages'][1]['content']))
            return {'choices': [{'message': {'content': 'ok'}}]}
        with keys(GROQ_API_KEY='q', GROQ_MODELS='a'):
            with mock.patch.object(C, 'http_json', side_effect=fake):
                C.run('p', 'x' * 500_000, sleep=lambda s: None)
        self.assertLess(seen[0], C.BUDGET['groq'] + 200)

    def test_main_writes_answer_and_returns_zero(self):
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('prompt')
        out = io.StringIO()
        with mock.patch.object(C, 'run', return_value=('groq', 'm', 'جواب')), \
                mock.patch.object(sys, 'stdin', io.StringIO('ctx')), mock.patch.object(sys, 'stdout', out):
            self.assertEqual(C.main(['', f.name]), 0)
        self.assertEqual(out.getvalue().strip(), 'جواب')
        os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
