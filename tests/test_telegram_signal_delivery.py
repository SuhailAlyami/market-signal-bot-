import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from telegram_signal_delivery import send_once,verify_once,deliver


class TelegramTests(unittest.TestCase):
    def test_single_verification_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory,patch('telegram_signal_delivery.load_credentials',return_value={'token':'test','chat_id':'test'}),patch('telegram_signal_delivery.urllib.request.urlopen') as network:
            network.return_value.__enter__.return_value.read.return_value=b'{"ok":true,"result":{"message_id":7}}'
            self.assertEqual(verify_once(directory,{'status':'ok'})['message_id'],7)
            self.assertIsNone(verify_once(directory,{'status':'ok'}));self.assertEqual(network.call_count,1)

    def test_unknown_delivery_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as directory,patch('telegram_signal_delivery.urllib.request.urlopen',side_effect=TimeoutError) as network:
            receipt=Path(directory)/'r.json'
            self.assertEqual(send_once({'token':'test','chat_id':'test'},'TEST',receipt)['status'],'uncertain_no_automatic_resend')
            self.assertEqual(send_once({'token':'test','chat_id':'test'},'TEST',receipt)['status'],'deduplicated')
            self.assertEqual(network.call_count,1)

    def test_missing_credentials_do_not_send(self):
        with tempfile.TemporaryDirectory() as directory,patch('telegram_signal_delivery.load_credentials',return_value=None),patch('telegram_signal_delivery.urllib.request.urlopen') as network:
            self.assertEqual(verify_once(directory,{'status':'ok'})['status'],'telegram_credentials_unavailable')
            self.assertEqual(deliver([],{},directory),[]);network.assert_not_called()

    def test_invalid_signal_fails_shared_gate(self):
        with tempfile.TemporaryDirectory() as directory,patch('telegram_signal_delivery.load_credentials',return_value={'token':'test','chat_id':'test'}),patch('telegram_signal_delivery.urllib.request.urlopen') as network:
            result=deliver([{'event_id':'x'}],{'status':'degraded'},directory)
            self.assertEqual(result[0]['status'],'blocked');network.assert_not_called()
