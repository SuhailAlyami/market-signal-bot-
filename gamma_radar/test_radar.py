"""Offline tests for the gamma radar (synthetic chain, no network)."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'range_alert'))
import radar as G  # noqa: E402
import daily_range as D  # noqa: E402

NOW = datetime(2026, 11, 19, 13, 0, tzinfo=timezone.utc)


def chain(spot, legs):
    return {'timestamp': 't', 'data': {'current_price': spot, 'prev_day_close': spot, 'last_trade_time': 'x',
            'options': [{'option': f'SPXW261120{cp}{int(k*1000):08d}', 'open_interest': oi, 'iv': .2,
                         'gamma': G.bs_gamma(spot, k, 1/365, .2)} for cp, k, oi in legs]}}


class RadarTests(unittest.TestCase):
    def test_symbol_parse(self):
        o = G.parse({'option': 'SPXW261120P07400000', 'open_interest': 5, 'iv': .2, 'gamma': .001})
        self.assertEqual((o['root'], o['cp'], o['k'], o['exp'].day), ('SPXW', 'P', 7400.0, 20))
        self.assertIsNone(G.parse({'option': 'BAD'}))

    def test_put_heavy_chain_is_negative_and_call_heavy_positive(self):
        neg = G.analyse(chain(7300, [('P', 7300, 50000), ('C', 7300, 1000)]), now=NOW)
        pos = G.analyse(chain(7300, [('C', 7300, 50000), ('P', 7300, 1000)]), now=NOW)
        self.assertEqual(neg['regime'], 'negative'); self.assertLess(neg['net_gamma_bn_per_1pct'], 0)
        self.assertEqual(pos['regime'], 'positive'); self.assertGreater(pos['net_gamma_bn_per_1pct'], 0)

    def test_flip_between_put_and_call_concentrations(self):
        r = G.analyse(chain(7300, [('P', 7200, 40000), ('C', 7400, 40000)]), now=NOW)
        self.assertIsNotNone(r['flip'])
        self.assertTrue(7200 < r['flip'] < 7400)
        self.assertEqual((r['call_wall'], r['put_wall']), (7400.0, 7200.0))
        self.assertEqual([x['k'] for x in r['levels']], [7400.0, 7200.0])
        self.assertGreater(r['levels'][0]['gex_bn'], 0); self.assertLess(r['levels'][1]['gex_bn'], 0)

    def test_expired_and_zero_oi_ignored(self):
        r = G.analyse(chain(7300, [('C', 7300, 0)]), now=NOW)
        self.assertEqual(r['n_options'], 0)

    def test_morning_line(self):
        line = D.gamma_line({'regime': 'negative', 'flip': 7482.9, 'call_wall': 7700.0, 'put_wall': 7000.0})
        self.assertIn('سالب', line); self.assertIn('الانقلاب 7,483', line); self.assertIn('دعم 7,000', line)
        line2 = D.gamma_line({'regime': 'negative', 'levels': [{'k': 7250.0, 'gex_bn': 1.2}, {'k': 7100.0, 'gex_bn': -3.4}]})
        self.assertIn('7,250+، 7,100−', line2)


class IntradayTests(unittest.TestCase):
    def test_crossing_events(self):
        import intraday as I
        cur = {'spot': 7290, 'flip': 7300, 'levels': [{'k': 7295, 'gex_bn': -2.0}, {'k': 7280, 'gex_bn': 1.0}]}
        ev = I.events({'spot': 7310}, cur)
        self.assertIn({'type': 'into_negative_gamma', 'level': 7300}, ev)
        self.assertIn({'type': 'crossed_negative_level_down', 'level': 7295}, ev)
        self.assertEqual(len(ev), 2)                     # positive-gamma 7280 not crossed and not counted
        self.assertEqual(I.events(None, cur), [])

    def test_session_gate_and_append(self):
        import tempfile
        import intraday as I
        self.assertIsNone(I.run('/nonexistent', now=datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)))  # Saturday
        now = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)                                           # 10:00 NY
        with tempfile.TemporaryDirectory() as t:
            I.run(t, now=now, chain=chain(7390, [('P', 7300, 40000), ('C', 7400, 40000)]))
            r = I.run(t, now=now, chain=chain(7250, [('P', 7300, 40000), ('C', 7400, 40000)]))
            lines = Path(t, '2026-11-20.jsonl').read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(e['type'] == 'into_negative_gamma' for e in r['events']))


class EveningGammaTests(unittest.TestCase):
    def test_line_and_tally(self):
        import json, tempfile
        import evaluate_range as E
        call = {'session': '2026-11-19', 'prev_close': 7323.63, 'm': 113.3, 'direction': 'up', 'conf': 89, 'method': 'gap',
                'levels': [{'k': .1, 'high': 7418, 'low': 7395, 'p_high': 85, 'p_low': 80}], 'range': [7210, 7437],
                'gamma': {'regime': 'negative', 'flip': 7482.9, 'call_wall': 7700, 'put_wall': 7000}}
        with tempfile.TemporaryDirectory() as t:
            Path(t, '2026-11-19.json').write_text(json.dumps(call))
            spx = {'2026-11-18': (0, 0, 0, 7323.63), '2026-11-19': (7389.26, 7415.64, 7173.63, 7175.83)}
            text = '\n'.join(E.call_lines(t, spx, '2026-11-19'))
        self.assertIn('رادار الغاما: سالب — حركة قوية: حدثت', text)
        self.assertIn('الغاما السالبة: انفجار 1/1، الموجبة 0/0', text)


if __name__ == '__main__':
    unittest.main()
