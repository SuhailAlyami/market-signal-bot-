import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from research_spx_premove import directions, features
from research_spx_preparation import MODEL, VALIDATION, readiness, run_validation, schedule


class PreparationTests(unittest.TestCase):
    def test_readiness_precedes_crossing_while_entry_trigger_is_absent(self):
        f = pd.DataFrame(dict(ema5=[101., 101.], ema15=[100., 100.],
                              move15=[1., 1.], previous_close=[100., 100.],
                              previous_ema5=[101., 101.], close=[100.5, 101.5],
                              body=[.5, .5], valid=[True, True]),
                         index=pd.date_range('2026-07-20T14:00Z', periods=2, freq='min'))
        self.assertEqual(readiness(f).tolist(), [1, 0])
        self.assertEqual(directions(f, 'pullback_release').tolist(), [0, 1])
        f.loc[:, 'valid'] = False
        self.assertEqual(readiness(f).tolist(), [0, 0])

    def test_future_prices_do_not_change_completed_prefix_decisions(self):
        prices = [100 + i * .1 for i in range(90)]
        prices[36:39] = [103.2, 103.25, 103.45]
        opens = [prices[0] - .05, *prices[:-1]]
        bars = pd.DataFrame(dict(Open=opens, High=[max(o, c) + .2 for o, c in zip(opens, prices)],
                                 Low=[min(o, c) - .2 for o, c in zip(opens, prices)], Close=prices),
                            index=pd.date_range('2026-07-20T13:30Z', periods=90, freq='min'))
        bars.attrs.update(symbol='SPX', security_type='IND')
        original_features = features(bars)
        changed = bars.copy()
        changed.iloc[60:] += 50
        self.assertEqual(readiness(original_features).iloc[:60].tolist(),
                         readiness(features(changed)).iloc[:60].tolist())
        original = [s for s in schedule(original_features, MODEL) if s['index'] < 60]
        actual = [s for s in schedule(features(changed), MODEL) if s['index'] < 60]
        self.assertGreater(len(original), 0, 'Causality comparison needs an actual readiness signal')
        self.assertEqual(original, actual)

    def test_direction_symmetry(self):
        f = pd.DataFrame(dict(ema5=[101.], ema15=[100.], move15=[1.],
                              previous_close=[100.], previous_ema5=[101.], close=[100.5],
                              body=[.5], valid=[True]))
        mirrored = f.copy()
        for column in ('ema5', 'ema15', 'previous_close', 'previous_ema5', 'close'):
            mirrored[column] = 300 - f[column]
        mirrored['move15'], mirrored['body'] = -f.move15, -f.body
        self.assertEqual(readiness(f).tolist(), [1])
        self.assertEqual(readiness(mirrored).tolist(), [-1])

    def test_validation_reservation_survives_another_output_filename(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / 'previous.json'
            previous.write_text(json.dumps(dict(holdout_opened=False,
                                                splits={'holdout': VALIDATION},
                                                manifest_sha256='same-input')), encoding='utf-8')
            evaluated = {'models': {MODEL: {'strict': {'0': {}}}}}
            with patch('research_spx_preparation.load_capture',
                       return_value=({day: None for day in VALIDATION}, [], 'same-input')), \
                 patch('research_spx_preparation.evaluate_partition', return_value=evaluated) as evaluate, \
                 patch('research_spx_preparation.quality_gate', return_value={'passed': False}):
                run_validation('unused', previous, root / 'first.json', root / 'registry')
                with self.assertRaises(FileExistsError):
                    run_validation('unused', previous, root / 'second.json', root / 'registry')
                self.assertEqual(evaluate.call_count, 1)


if __name__ == '__main__':
    unittest.main()
