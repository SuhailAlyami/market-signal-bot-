import datetime as dt
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_context as B


class BuildContextTests(unittest.TestCase):
    def test_review_contains_rules_and_diff_and_is_capped(self):
        text = B.build_review('+x = 1\n' * 100_000, 'title: t')
        self.assertIn('AGENTS.md', text)
        self.assertIn('+x = 1', text)
        self.assertLessEqual(len(text), B.MAX_CHARS + 40)

    def test_focus_rotates_weekly_and_override_wraps(self):
        seen = {B.focus_index(dt.date(2026, 1, 5) + dt.timedelta(weeks=w)) for w in range(len(B.FOCI))}
        self.assertEqual(seen, set(range(len(B.FOCI))))
        self.assertEqual(B.focus_index(override=len(B.FOCI) + 1), 1)

    def test_every_focus_file_exists(self):
        for _, files in B.FOCI:
            for f in files:
                self.assertTrue((B.ROOT / f).is_file(), f)

    def test_audit_fits_budget_for_every_focus(self):
        for i in range(len(B.FOCI)):
            text, title = B.build_audit('run log', i)
            self.assertIn(title, text)
            self.assertLessEqual(len(text), B.MAX_CHARS + 40)

    def test_cli_writes_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / 'runs').write_text('x')
            B.main(['', 'audit', str(d / 'runs'), str(d / 'out'), '--focus', '3'])
            self.assertIn('FILE .github/workflows/', (d / 'out').read_text())


if __name__ == '__main__':
    unittest.main()
