from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from spx_price_runtime import SPXPriceRuntime
from test_spx_price_watch import frame


class SPXLifecycleTests(unittest.TestCase):
    def test_opposite_watch_cancels_active_before_confirmation_and_has_no_old_cooldown(self):
        for phase in ('SETUP', 'TRIGGER'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                data = frame(); data.iloc[30] = [100, 100.1, 98.9, 99]
                end = data.index[30].to_pydatetime()+timedelta(minutes=1)
                runtime = SPXPriceRuntime(Path(directory)/'state.json', Path(directory)/'journal.jsonl')
                runtime.state['symbols']['SPX'] = {'active': {'phase': phase, 'direction': 1,
                    'started_at': (end-timedelta(minutes=1)).isoformat(), 'level': 98,
                    'atr': 1, 'invalidation': 90, 'confirmation_bars': 1},
                    'last_bar_end': (end-timedelta(minutes=1)).isoformat()}
                events = runtime._process_bar('SPX', data, 30, end)
                self.assertEqual([e['state'] for e in events],
                                 ['EXIT' if phase == 'TRIGGER' else 'INVALIDATION', 'SETUP'])
                self.assertEqual(events[-1]['direction'], 'DOWN')
                self.assertEqual(events[-1]['detector'], 'spx-price-watch-v1')
                self.assertEqual(events[-1]['pattern'], 'LOCAL_BREAK')
                self.assertFalse(events[-1]['notify_eligible'])
                self.assertEqual(runtime.state['symbols']['SPX']['active']['direction'], -1)
                self.assertEqual(runtime._process_bar('SPX', data, 30, end), [])

    def test_injected_calendar_controls_poll_even_when_futures_calendar_disagrees(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = SPXPriceRuntime(Path(directory)/'state.json', Path(directory)/'journal.jsonl')
            runtime.market_is_open = lambda now: False
            data = frame()
            def forbidden(symbol):
                raise AssertionError('closed cash session must not fetch')
            result = runtime.poll(data.index[-1].to_pydatetime(), forbidden)
            self.assertEqual(result['heartbeat']['symbols']['SPX']['status'], 'closed')
            self.assertEqual(result['events'], [])


if __name__ == '__main__':
    unittest.main()
