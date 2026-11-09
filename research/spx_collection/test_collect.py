import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import collect_yahoo_spx as c


def response(days, drop=(), null=(), step=1, base=100.0):
    """Synthetic Yahoo body; days are full regular sessions built from NY wall-clock times."""
    ts, o, h, lo, cl, v = [], [], [], [], [], []
    for day in days:
        opening = c.CAL.session_open(day).to_pydatetime().astimezone(c.NY)
        closing = c.CAL.session_close(day).to_pydatetime().astimezone(c.NY)
        n = int((closing-opening).total_seconds()//60)
        for i in range(0, n, step):
            at = opening+timedelta(minutes=i)
            if (day, i) in drop:
                continue
            p = base+i*.01
            ts.append(int(at.timestamp())); v.append(0 if i == 5 else 10)
            bad = (day, i) in null
            o.append(None if bad else p); h.append(p+.5); lo.append(p-.5); cl.append(p+.1)
    last = ts[-1]
    return json.dumps({'chart': {'error': None, 'result': [{'meta': {'regularMarketTime': last, 'exchangeTimezoneName': 'America/New_York',
                       'dataGranularity': '1m', 'instrumentType': 'INDEX'}, 'timestamp': ts,
                       'indicators': {'quote': [{'open': o, 'high': h, 'low': lo, 'close': cl, 'volume': v}]}}]}}).encode()


def meta(at):
    return {'requested_at': at.isoformat(), 'received_at': at.isoformat(), 'http_seconds': .1, 'host': 'x', 'url': 'x', 'status': 200}


AFTER = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


class CollectorTests(unittest.TestCase):
    def test_complete_sessions_across_dst_change(self):
        # 2026-10-30 is EDT, 2026-11-02 is EST after the Nov 1 change; both must give a 390-row grid at 09:30 NY.
        with tempfile.TemporaryDirectory() as d:
            snap = c.run(response(['2026-10-30', '2026-11-02']), meta(AFTER), Path(d))
            self.assertEqual(snap['sessions_added'], ['2026-10-30', '2026-11-02'])
            store = json.loads((Path(d)/'sessions.json').read_text())
            for day in store:
                rows = store[day]['csv'].splitlines()
                self.assertEqual((len(rows)-1, rows[1][:5], rows[-1][:5]), (390, '09:30', '15:59'))
            self.assertEqual(store['2026-11-02']['zero_volume_bars'], 1)

    def test_missing_minute_makes_day_incomplete_and_nothing_is_filled(self):
        with tempfile.TemporaryDirectory() as d:
            snap = c.run(response(['2026-11-05'], drop={('2026-11-05', 100)}), meta(AFTER), Path(d))
            self.assertEqual(snap['sessions_added'], [])
            self.assertEqual(snap['incomplete_days'][0]['reason'], 'incomplete_regular_grid')
            self.assertEqual(snap['incomplete_days'][0]['present'], 389)

    def test_null_bar_is_dropped_not_interpolated(self):
        bars, m = c.parse(response(['2026-11-05'], null={('2026-11-05', 7)}))
        self.assertEqual((len(bars), m['dropped_invalid_bars']), (389, 1))
        self.assertNotIn(datetime(2026, 11, 5, 9, 37, tzinfo=c.NY), [b['at'] for b in bars])

    def test_forming_bar_excluded_and_age_reported(self):
        body = response(['2026-11-05'])
        bars, _ = c.parse(body)
        now = bars[-1]['at'].astimezone(timezone.utc)+timedelta(seconds=30)  # last bar still forming
        done = c.completed_only(bars, now)
        self.assertEqual(len(done), len(bars)-1)
        with tempfile.TemporaryDirectory() as d:
            snap = c.run(body, meta(now), Path(d))
            self.assertEqual(snap['sessions_added'], [])  # session not complete at receipt
            self.assertEqual(snap["last_completed_bar_age_seconds"], 30.0)

    def test_first_read_kept_and_revisions_logged(self):
        with tempfile.TemporaryDirectory() as d:
            c.run(response(['2026-11-05']), meta(AFTER), Path(d))
            first = (Path(d)/'sessions.json').read_text()
            changed = json.loads(response(['2026-11-05']))
            changed['chart']['result'][0]['indicators']['quote'][0]['open'][10] += .05
            snap = c.run(json.dumps(changed).encode(), meta(AFTER+timedelta(hours=1)), Path(d))
            self.assertEqual(snap['sessions_revised_not_applied'], ['2026-11-05'])
            store = json.loads((Path(d)/'sessions.json').read_text())
            self.assertEqual(store['2026-11-05']['csv'], json.loads(first)['2026-11-05']['csv'])
            self.assertEqual(len(store['2026-11-05']['later_differing_reads']), 1)

    def test_consumed_flag_and_classification(self):
        with tempfile.TemporaryDirectory() as d:
            snap = c.run(response(['2026-11-04', '2026-11-05']), meta(AFTER), Path(d))
            store = json.loads((Path(d)/'sessions.json').read_text())
            self.assertTrue(store['2026-11-04']['consumed_in_prior_research'])
            self.assertFalse(store['2026-11-05']['consumed_in_prior_research'])
            self.assertEqual(snap['classification'], 'DELAYED_RESEARCH_ONLY')

    def test_provider_error_raises(self):
        with self.assertRaises(ValueError):
            c.parse(json.dumps({'chart': {'error': {'code': 'x'}, 'result': None}}).encode())


if __name__ == '__main__':
    unittest.main()


class VerifyTests(unittest.TestCase):
    def store(self, days, **kw):
        bars, _ = c.parse(response(days, **kw))
        s, _ = c.build_sessions(bars)
        return s

    def test_contiguous_store_passes(self):
        r = c.verify(self.store(['2026-11-04', '2026-11-05', '2026-11-06']))
        self.assertEqual((r['ok'], r['complete_sessions']), (True, 3))

    def test_missing_calendar_session_is_flagged(self):
        r = c.verify(self.store(['2026-11-04', '2026-11-06']))  # 11-05 missing
        self.assertFalse(r['ok'])
        self.assertEqual(r['problems'], [{'day': '2026-11-05', 'problem': 'session_missing_from_store'}])

    def test_tampered_grid_and_ohlc_are_flagged(self):
        st = self.store(['2026-11-05', '2026-11-06'])
        lines = st['2026-11-05']['csv'].splitlines()
        del lines[50]
        st['2026-11-05']['csv'] = '\n'.join(lines)+'\n'
        parts = st['2026-11-06']['csv'].splitlines()
        t, o, h, lo, cl = parts[10].split(',')
        parts[10] = f'{t},{o},{float(h)-5},{lo},{cl}'
        st['2026-11-06']['csv'] = '\n'.join(parts)+'\n'
        r = c.verify(st)
        self.assertEqual({p['problem'] for p in r['problems']}, {'grid_mismatch', 'invalid_ohlc'})

    def test_weekend_and_holiday_gaps_are_not_false_alarms(self):
        # 2026-11-06 (Fri) -> 2026-11-09 (Mon): no calendar session in between
        r = c.verify(self.store(['2026-11-06', '2026-11-09']))
        self.assertTrue(r['ok'])


class DedupeAndStatusTests(unittest.TestCase):
    def test_identical_payload_writes_nothing_second_time(self):
        with tempfile.TemporaryDirectory() as d:
            body = response(['2026-11-05'])
            c.run(body, meta(AFTER), Path(d))
            before = sorted(p.name for p in (Path(d)/'raw').iterdir()), (Path(d)/'snapshots.jsonl').read_text()
            r = c.run(body, meta(AFTER+timedelta(hours=3)), Path(d))
            self.assertEqual(r['status'], 'DUPLICATE_PAYLOAD_SKIPPED')
            self.assertEqual(before, (sorted(p.name for p in (Path(d)/'raw').iterdir()), (Path(d)/'snapshots.jsonl').read_text()))

    def test_retained_raw_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'x.gz'
            c.write_new(p, b'a')
            c.write_new(p, b'a')  # identical rewrite tolerated
            with self.assertRaises(RuntimeError):
                c.write_new(p, b'b')
            self.assertEqual(p.read_bytes(), b'a')

    def test_market_status_distinguishes_preopen_open_close_weekend_holiday(self):
        u = lambda *a: datetime(*a, tzinfo=timezone.utc)
        self.assertEqual(c.market_status(u(2026, 11, 9, 5, 54))['state'], 'PRE_OPEN')  # Monday before 09:30 ET
        s = c.market_status(u(2026, 11, 9, 15, 0))
        self.assertEqual((s['state'], s['open_riyadh'], s['close_riyadh']), ('OPEN', '17:30', '00:00'))
        self.assertEqual(c.market_status(u(2026, 11, 9, 21, 30))['state'], 'POST_CLOSE')
        self.assertEqual((c.market_status(u(2026, 11, 8, 15))['state'], c.market_status(u(2026, 11, 8, 15))['reason']), ('NO_SESSION', 'WEEKEND'))
        h = c.market_status(u(2026, 11, 26, 15))  # Thanksgiving: a weekday holiday, not a weekend
        self.assertEqual((h['state'], h['reason']), ('NO_SESSION', 'HOLIDAY'))

    def test_market_status_early_close_and_dst_riyadh_times(self):
        e = c.market_status(datetime(2026, 11, 27, 15, tzinfo=timezone.utc))  # day after Thanksgiving, 13:00 ET close
        self.assertEqual((e['state'], e['early_close'], e['close_riyadh']), ('OPEN', True, '21:00'))
        summer = c.market_status(datetime(2026, 7, 15, 15, tzinfo=timezone.utc))  # EDT: 20:00 UTC close
        self.assertEqual((summer['open_riyadh'], summer['close_riyadh']), ('16:30', '23:00'))


class BreadthCollectionTests(unittest.TestCase):
    DAYS = ['2026-11-05', '2026-11-06']  # synthetic bodies only; no real data for these dates is read

    def fetched(self, drop=None, fail=None, days=None):
        out = []
        for k, sym in enumerate(c.BREADTH_SYMBOLS):
            if sym == fail:
                out.append((sym, None, {'failed_at': AFTER.isoformat(), 'error': 'URLError(timeout)'}))
                continue
            d = drop.get(sym, ()) if drop else ()
            out.append((sym, response(days or self.DAYS, drop=d, step=5, base=100.0+k), meta(AFTER)))
        return out

    def test_universe_matches_frozen_protocol_order(self):
        self.assertEqual(c.BREADTH_SYMBOLS, ['^GSPC', 'NVDA', 'MSFT', 'AAPL', 'AMZN', 'GOOGL', 'META', 'AVGO', 'TSLA', 'BRK-B', 'JPM'])

    def test_all_symbols_stored_synchronized_with_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            r = c.run_breadth(self.fetched(), Path(d))
            self.assertEqual((r['failures'], r['coverage']['ok'], r['coverage']['synchronized_days']), ([], True, self.DAYS))
            store = json.loads((Path(d)/'breadth5m/bars5m.json').read_text())
            self.assertEqual(sorted(store), sorted(c.BREADTH_SYMBOLS))
            rows = store['NVDA']['2026-11-05']['csv'].splitlines()
            self.assertEqual((len(rows)-1, rows[1][:5], rows[-1][:5], store['NVDA']['2026-11-05']['step']), (78, '09:30', '15:55', 5))
            snaps = [json.loads(x) for x in (Path(d)/'breadth5m/snapshots.jsonl').read_text().splitlines()]
            self.assertEqual(len(snaps), 11)
            self.assertTrue(all({'requested_at', 'received_at', 'raw_sha256', 'symbol'} <= set(x) for x in snaps))
            self.assertEqual(len(list((Path(d)/'breadth5m/raw').iterdir())), 11)
            self.assertFalse((Path(d)/'sessions.json').exists())  # SPX 1m store untouched by breadth collection

    def test_missing_bar_breaks_synchronization_and_is_not_filled(self):
        with tempfile.TemporaryDirectory() as d:
            r = c.run_breadth(self.fetched(drop={'JPM': {('2026-11-06', 50)}}), Path(d))
            cov = r['coverage']
            self.assertFalse(cov['ok'])
            self.assertEqual(cov['synchronized_days'], ['2026-11-05'])
            self.assertEqual(cov['missing'], [{'day': '2026-11-06', 'symbols': ['JPM']}])
            self.assertEqual(r['per_symbol']['JPM']['incomplete'][0]['reason'], 'incomplete_regular_grid')

    def test_fetch_failure_recorded_and_reported(self):
        with tempfile.TemporaryDirectory() as d:
            r = c.run_breadth(self.fetched(fail='TSLA'), Path(d))
            self.assertEqual(r['failures'], ['TSLA'])
            self.assertFalse(r['coverage']['ok'])
            snaps = [json.loads(x) for x in (Path(d)/'breadth5m/snapshots.jsonl').read_text().splitlines()]
            self.assertEqual([x['status'] for x in snaps if x['symbol'] == 'TSLA'], ['FETCH_FAILED'])

    def test_rerun_dedupes_and_keeps_first_read(self):
        with tempfile.TemporaryDirectory() as d:
            c.run_breadth(self.fetched(), Path(d))
            first = (Path(d)/'breadth5m/bars5m.json').read_text()
            r = c.run_breadth(self.fetched(), Path(d))
            self.assertTrue(all(v == 'DUPLICATE_PAYLOAD_SKIPPED' for v in r['per_symbol'].values()))
            self.assertEqual(first, (Path(d)/'breadth5m/bars5m.json').read_text())
            self.assertEqual(len(list((Path(d)/'breadth5m/raw').iterdir())), 11)

    def test_forming_5m_bar_excluded(self):
        bars, _ = c.parse(response(['2026-11-05'], step=5))
        at_last = bars[-1]['at'].astimezone(timezone.utc)
        self.assertEqual(len(c.completed_only(bars, at_last+timedelta(minutes=4), minutes=5)), len(bars)-1)
        self.assertEqual(len(c.completed_only(bars, at_last+timedelta(minutes=5), minutes=5)), len(bars))

    def test_url_encodes_symbols(self):
        self.assertIn('/chart/%5EGSPC?', 'https://h/v8/finance/chart/' + c.urllib.parse.quote('^GSPC', safe='') + '?')
        self.assertEqual(c.urllib.parse.quote('BRK-B', safe=''), 'BRK-B')
