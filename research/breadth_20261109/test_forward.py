"""Tests for the input/date separation of the frozen breadth screen. Uses the development fixture (consumed dates)
and synthetic data only; no session >= 2026-11-05 of real data is read."""
import gzip
import hashlib
import json
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent/'spx_collection'))
import collect_yahoo_spx as col  # noqa: E402
import run as R  # noqa: E402  (breadth run.py; wave_capture is loaded under another name by breadth_core)
from breadth_core import UNIVERSE, evaluate, signal_rows  # noqa: E402
from inputs import dev_inputs, forward_inputs  # noqa: E402

FROZEN_HASHES = {  # recorded in objective_review_20261107/wave_capture/MANIFEST.json before this refactor
    HERE.parent/'objective_review_20261107/objective_review.py': '19f5da59887323b4ccec0dcfe232f35a5184ecf6f362f07d428f48e6709f003a',
    HERE.parent/'objective_review_20261107/wave_capture/run.py': 'c0c3c535c14859c8b527ec9add71ed03d1414b04af8be31f509b5f4d82e71405'}


def dev_json():
    out = evaluate(*dev_inputs()); out.pop('_rows')
    return json.dumps(out, indent=1)


def store_from_dev_raw():
    store = {}
    far = datetime(2030, 1, 1, tzinfo=timezone.utc)
    for sym in col.BREADTH_SYMBOLS:
        body = gzip.open(HERE/'raw'/f"{sym.replace('^', '')}_5m_60d.json.gz").read()
        bars, _ = col.parse(body)
        sessions, _ = col.build_sessions(col.completed_only(bars, far, minutes=5), step=5)
        store[sym] = sessions
    return store


def synthetic_store(days, seed=7):
    rng = random.Random(seed)
    store = {}
    for k, sym in enumerate(col.BREADTH_SYMBOLS):
        bars, p = [], 100.0+10*k
        for day in days:
            op = col.CAL.session_open(day).to_pydatetime().astimezone(col.NY)
            for i in range(78):
                o = p; p = max(1.0, p+rng.gauss(0, 2.0 if sym == '^GSPC' else .3))
                bars.append({'at': op+timedelta(minutes=5*i), 'open': o, 'high': max(o, p)+.1, 'low': min(o, p)-.1, 'close': p, 'volume': 1})
        store[sym], _ = col.build_sessions(bars, step=5)
    return store


class ForwardInputTests(unittest.TestCase):
    def test_development_output_byte_identical_to_original_result(self):
        self.assertEqual(dev_json(), (HERE/'result.json').read_text())

    def test_frozen_dependencies_and_protocol_unchanged(self):
        for path, h in FROZEN_HASHES.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), h, path.name)
        self.assertEqual(hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
                         json.loads((HERE/'result.json').read_text())['protocol_sha256'])

    def test_collector_store_path_equals_dev_path_on_consumed_dates(self):
        lo, hi = '2026-10-29', '2026-11-04'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bars5m.json'
            p.write_text(json.dumps(store_from_dev_raw()))
            fs, fe, fc = forward_inputs(p, lo, hi, allow_consumed=True)
        ds, de, dc = dev_inputs()
        ds = [s for s in ds if lo <= s[0] <= hi]
        self.assertEqual([(s[0], s[1], s[3], s[4]) for s in fs], [(s[0], s[1], s[3], s[4]) for s in ds])
        self.assertEqual(fe, [])
        a = evaluate(fs, [], fc); b = evaluate(ds, [], dc)
        a.pop('_rows'); b.pop('_rows')
        self.assertEqual(a, b)
        self.assertGreater(a['all']['n'], 0)

    def test_forward_refuses_consumed_dates_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'s.json'; p.write_text('{}')
            with self.assertRaises(ValueError):
                forward_inputs(p, '2026-11-04')

    def test_missing_symbol_day_excluded_with_reason(self):
        days = ['2026-11-05', '2026-11-06']
        st = synthetic_store(days)
        del st['JPM']['2026-11-06']
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'s.json'; p.write_text(json.dumps(st))
            sessions, excluded, closes = forward_inputs(p)
        self.assertEqual([s[0] for s in sessions], ['2026-11-05'])
        self.assertEqual(excluded, [{'day': '2026-11-06', 'reason': 'missing_symbols', 'symbols': ['JPM']}])
        self.assertTrue(all(datetime(2026, 11, 6, 10, tzinfo=col.NY) not in closes[u] for u in UNIVERSE))

    def test_guard_computes_no_outcomes_before_minimum_events(self):
        days = [str(t.date()) for t in col.CAL.sessions_in_range('2026-11-05', '2026-11-13')]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'s.json'; p.write_text(json.dumps(synthetic_store(days)))
            out = R.run_forward(p)
        self.assertEqual(out['status'], 'NOT_ENOUGH_EVENTS_NO_OUTCOMES_COMPUTED')
        self.assertLess(out['high_agreement_events'], 190)
        self.assertFalse({'high', 'rest', 'C1', 'C4', 'checks', 'decision'} & set(out))

    def test_outcome_free_counting_matches_scored_agreement(self):
        days = [str(t.date()) for t in col.CAL.sessions_in_range('2026-11-05', '2026-11-13')]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'s.json'; p.write_text(json.dumps(synthetic_store(days)))
            sessions, _, closes = forward_inputs(p)
        a, _ = signal_rows(sessions, closes, scored=False)
        b, _ = signal_rows(sessions, closes, scored=True)
        self.assertGreater(len(a), 0)
        self.assertEqual({(x['day'], x['side'], x['agree']) for x in b} <= {(x['day'], x['side'], x['agree']) for x in a}, True)

    def test_all_criteria_required_and_minimum_kept(self):
        self.assertEqual(R.FP['minimum_high_agreement_events'], 190)
        self.assertEqual(sorted(R.FP['acceptance_all_required']), ['C1', 'C2', 'C3', 'C4', 'C5'])
        ok = {k: True for k in ('C1', 'C2', 'C3', 'C4', 'C5')}
        self.assertEqual(R.forward_decision(ok), 'FORWARD_PASS_STILL_NOT_READY')
        for k in ok:
            self.assertEqual(R.forward_decision(dict(ok, **{k: False})), 'FORWARD_FAIL')


if __name__ == '__main__':
    unittest.main()
