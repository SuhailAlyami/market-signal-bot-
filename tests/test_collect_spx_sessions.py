import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import unittest

from collect_spx_sessions import collect, request_end, sessions, validate_session


def bars(opened, closed):
    return [{'time': str(int(t.timestamp())), 'open': 10, 'high': 12,
             'low': 9, 'close': 11, 'volume': '-1'}
            for t in pd.date_range(opened, closed, freq='min', inclusive='left')]


class CollectorTests(unittest.TestCase):
    def test_nyse_early_close_holiday_and_dst(self):
        plan = sessions('2026-11-30', 3, now='2026-12-01T00:00Z')
        assert [x[0] for x in plan] == ['2026-11-25', '2026-11-27', '2026-11-30']
        assert request_end(plan[1][2]) == '20261127-18:00:00'
        assert len(bars(plan[1][1], plan[1][2])) == 210
        assert request_end(sessions('2026-10-21', 1, now='2026-10-22T00:00Z')[0][2]) == '20261021-20:00:00'


    def test_missing_conflicts_and_raw_rows_unchanged(self):
        _, opened, closed = sessions('2026-10-21', 1, now='2026-10-22T00:00Z')[0]
        rows = bars(opened, closed)
        assert validate_session(rows, opened, closed)['complete']
        assert validate_session(rows[:-1], opened, closed)['missing_minutes'] == ['2026-10-21T19:59:00+00:00']
        duplicate = [rows[0], *rows]
        assert validate_session(duplicate, opened, closed)['identical_duplicates'] == 1
        assert rows[0]['volume'] == '-1'
        with self.assertRaisesRegex(ValueError, 'conflicting_duplicate'):
            validate_session([dict(rows[0], close=10), *rows], opened, closed)


    def test_mocked_acquisition_uses_different_daily_bounds_and_disconnects(self):
        class Fake:
            disconnected = False

            def resolve(self):
                return type('Contract', (), {'conId': 123})()

            def history(self, contract, close, request_id):
                self.ends.append(request_end(close))
                opened = close - pd.Timedelta(minutes=390)
                return bars(opened, close), {'start': 'original start', 'end': 'original end'}

            def disconnect(self):
                self.disconnected = True

        fake = Fake()
        fake.ends = []
        with tempfile.TemporaryDirectory() as root:
            with patch('collect_spx_sessions.gateway', return_value=fake), patch('collect_spx_sessions.time.sleep'):
                report = collect('2026-10-21', 2, Path(root) / 'capture')
            assert report['data_complete']
            assert fake.ends == ['20261020-20:00:00', '20261021-20:00:00']
            assert fake.disconnected
            assert report['readiness'] == 'NOT_READY'


    def test_failure_is_sanitized_and_never_claims_complete(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('collect_spx_sessions.gateway', side_effect=RuntimeError('private provider details')):
                report = collect('2026-10-21', 1, Path(root) / 'capture')
            assert not report['data_complete']
            assert report['failure'] == 'RuntimeError'
            assert 'private provider details' not in (Path(root) / 'capture' / 'manifest.json').read_text()
