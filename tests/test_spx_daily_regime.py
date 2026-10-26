import unittest
import json
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from test_spx_daily import fixture
from spx_daily_regime import forecast_regime,regime_features,weighted_quantile
from evaluate_spx_daily import evaluate,compare

class RegimeTests(unittest.TestCase):
    def test_invalid_feed_is_recorded_without_forecasting(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'input.json'; output=Path(directory)/'result.json'
            rows=fixture(); rows[30]['close']=rows[30]['high']+1
            source.write_text(json.dumps(dict(source='IBKR',symbol='SPX',security_type='IND',bars=rows)))
            argv=['evaluate_spx_daily.py','--input',str(source),'--validation-start','2025-04-01',
                  '--holdout-start','2025-07-01','--output',str(output)]
            with patch('sys.argv',argv), patch('spx_daily_regime.forecast_regime') as model:
                runpy.run_module('evaluate_spx_daily',run_name='__main__')
            self.assertFalse(model.called)
            report=json.loads(output.read_text())
            self.assertEqual(report['status'],'WAIT_VALID_DATA')
            self.assertFalse(report['holdout_evaluated'])
            with patch('sys.argv',argv), self.assertRaises(FileExistsError):
                runpy.run_module('evaluate_spx_daily',run_name='__main__')

    def test_prefix_and_weights(self):
        rows=fixture()
        self.assertTrue(regime_features(rows[:90])[1].equals(regime_features(rows)[1].iloc[:90]))
        p=forecast_regime(rows[:90]); rows[-1]['close']=999999
        self.assertEqual(p,forecast_regime(rows[:90]))
        self.assertAlmostEqual(sum(p['analog_class_weights'].values()),1)
        self.assertLessEqual(p['predicted_low'],p['predicted_high'])
        self.assertIsNone(p['confidence'])
        self.assertTrue(np.allclose(weighted_quantile([3,1,2],[1,1,1],[.5]),[1.5]))

    def test_validation_failure_does_not_evaluate_holdout(self):
        rows=[dict(date=f'{i:04d}') for i in range(201)]
        with patch('evaluate_spx_daily.segment',return_value={'passed':False}) as run:
            report=evaluate(rows,'0081','0141')
        self.assertEqual(run.call_args.args[1:],(81,141))
        self.assertEqual(run.call_count,1)
        self.assertFalse(report['holdout_evaluated'])
        self.assertEqual(report['status'],'NOT_READY')

    def test_no_gain_and_missing_class_fail(self):
        records=[dict(date=str(i),direction_accuracy=1,actual_direction='Bullish',high_error=1,low_error=1) for i in range(60)]
        result=compare(records,records)
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['direction_gain'])
        self.assertFalse(result['checks']['all_actual_classes'])
        with self.assertRaises(ValueError):compare(records,list(reversed(records)))
