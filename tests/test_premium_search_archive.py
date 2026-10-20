from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from premium_archive import archive_history
from research_premium_search import candidate_rule, freeze, replicate
from test_premium_radar import bars, raw


class ArchiveTests(unittest.TestCase):
    def identity(self):
        return {'contract_id': 123, 'exchange': 'SMART', 'expiry': '2026-10-20',
                'side': 'CALL', 'strike': 7695., 'feed_status': 'REALTIME'}

    def test_unfinished_bars_excluded_receipt_and_revisions_retained(self):
        data = bars(3)
        first = data.index[1].to_pydatetime() + timedelta(seconds=30)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(archive_history(directory, self.identity(), raw(data), first), 1)
            self.assertEqual(archive_history(directory, self.identity(), raw(data), first), 0)
            revised = data.copy()
            revised.iloc[0, revised.columns.get_loc('Volume')] = 120.
            later = first + timedelta(minutes=1)
            self.assertEqual(archive_history(directory, self.identity(), raw(revised), later), 2)
            path = next((Path(directory)/'premium_bars').glob('*.jsonl'))
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]['received_at'], first.isoformat())
            self.assertNotEqual(records[0]['version_sha256'], records[1]['version_sha256'])
            self.assertEqual(records[0]['bar_start'], records[1]['bar_start'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_market_only_allowlist_excludes_account_and_tokens(self):
        data = bars(1)
        history = {**raw(data), 'access_token': 'secret', 'account': 'private'}
        identity = {**self.identity(), 'refresh_token': 'hidden'}
        with tempfile.TemporaryDirectory() as directory:
            archive_history(directory, identity, history, data.index[0].to_pydatetime()+timedelta(minutes=1))
            text = next((Path(directory)/'premium_bars').glob('*.jsonl')).read_text()
            self.assertNotIn('secret', text)
            self.assertNotIn('private', text)
            self.assertNotIn('hidden', text)

    def test_corruption_is_not_reset(self):
        data = bars(1)
        now = data.index[0].to_pydatetime()+timedelta(minutes=1)
        with tempfile.TemporaryDirectory() as directory:
            archive_history(directory, self.identity(), raw(data), now)
            next((Path(directory)/'premium_bars').glob('*.jsonl')).write_text('broken')
            with self.assertRaises(ValueError):
                archive_history(directory, self.identity(), raw(data), now)

    def test_invalid_identity_and_naive_clock(self):
        data = bars(1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                archive_history(directory, self.identity(), raw(data), data.index[0].to_pydatetime().replace(tzinfo=None))
            with self.assertRaises(ValueError):
                archive_history(directory, {**self.identity(), 'contract_id': '../bad'}, raw(data), data.index[0].to_pydatetime())


class SearchTests(unittest.TestCase):
    def test_fixed_grid_no_support_never_promotes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.json'
            path.write_text(json.dumps(raw(bars(30))))
            result = freeze([path])
            self.assertEqual(result['trial_count'], 18)
            self.assertIsNone(result['selected'])
            self.assertEqual(result['decision'], 'NOT_READY')
            self.assertFalse(result['notifications_enabled'])

    def test_replication_rejects_development_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.json'
            path.write_text(json.dumps(raw(bars(30))))
            frozen = freeze([path])
            frozen['selected'] = {'config': {'rvol': 2., 'return_1m': .03, 'distance': 1.5}}
            with self.assertRaisesRegex(ValueError, 'development_data_cannot'):
                replicate(frozen, [path])

    def test_candidate_never_uses_future_bars(self):
        from premium_radar import features
        data = bars(30)
        data.iloc[20] = [10., 11.1, 10., 11., 300.]
        rule = candidate_rule({'rvol': 2., 'return_1m': .03, 'distance': 1.5})
        expected = rule(features(data.iloc[:21], 20))
        data.iloc[21:] = [100., 110., 90., 105., 100000.]
        self.assertEqual(rule(features(data, 20)), expected)
        self.assertTrue(expected)


class RetentionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_collector_retains_both_option_histories(self):
        from ibkr_mcp import collect_spx
        from test_ibkr_mcp import FakeMarket, NOW
        feed = FakeMarket()
        data = bars(25)
        data.index = data.index - (data.index[-1] - NOW) - timedelta(minutes=1)

        async def call(name, args):
            return raw(data) if name == 'get_price_history' else await feed(name, args)

        with tempfile.TemporaryDirectory() as directory:
            records = []

            def sink(identity, history, received):
                records.append(archive_history(directory, identity, history, received))

            report = await collect_spx(call, now=NOW, history_sink=sink)
            self.assertEqual(records, [25, 25])
            self.assertEqual(len(list((Path(directory)/'premium_bars').glob('*.jsonl'))), 2)
            self.assertTrue(all(item['status'] == 'observed' for item in report['premium_radar']))
