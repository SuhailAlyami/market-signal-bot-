import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import notify_telegram as N


class NotifyTests(unittest.TestCase):
    def test_chunks_respect_telegram_limit_and_keep_text(self):
        text = ('سطر طويل ' * 50 + '\n') * 40 + 'x' * 9000
        parts = N.chunks(text)
        self.assertTrue(all(len(p) <= N.LIMIT for p in parts))
        self.assertEqual(''.join(parts), text)

    def test_short_report_is_one_message_with_header(self):
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('لا ملاحظات جدية')
        with mock.patch.object(N, 'send', return_value=True) as send:
            self.assertEqual(N.main(['', 'HEAD', f.name]), 0)
        send.assert_called_once_with('HEAD\n\nلا ملاحظات جدية')
        os.unlink(f.name)

    def test_failed_send_fails_the_step(self):
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False) as f:
            f.write('a')
        with mock.patch.object(N, 'send', return_value=False):
            self.assertEqual(N.main(['', 'H', f.name]), 1)
        os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
