import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from test_spx_daily import fixture
from spx_close_direction import features,predict,direction,evaluate,load_exports


class CloseDirectionTests(unittest.TestCase):
    def test_no_high_low_input_and_prefix_invariance(self):
        original=fixture()
        rows=[dict(date=r['date'],close=r['close']) for r in original]
        self.assertTrue(features(rows[:90])[1].equals(features(rows)[1].iloc[:90]))
        before=predict(rows[:90])
        original[50]['high']=-999;original[50]['low']=99999
        self.assertEqual(before,predict(original[:90]))
        rows[-1]['close']=99999
        self.assertEqual(before,predict(rows[:90]))
        self.assertIsNone(before['confidence'])
        self.assertTrue(all(np.isfinite(v) for v in before['class_scores'].values()))

    def test_neutral_definition_and_flat_history(self):
        self.assertEqual(direction(100,100.1),'Sideways')
        self.assertEqual(direction(100,99.9),'Sideways')
        self.assertEqual(direction(100,100.2),'Bullish')
        self.assertEqual(direction(100,99.8),'Bearish')
        rows=fixture()
        for r in rows:r['close']=100
        self.assertEqual(predict(rows)['direction'],'Sideways')

    def test_failed_validation_keeps_holdout_unevaluated(self):
        rows=[dict(date=f'{i:04d}') for i in range(201)]
        rows[81]['date']='2025-04-01';rows[141]['date']='2025-07-01'
        with patch('spx_close_direction.segment',return_value={'passed':False}) as run:
            report=evaluate(rows)
        run.assert_called_once_with(rows,81,141)
        self.assertFalse(report['holdout_evaluated'])
        self.assertFalse(report['high_low_used'])

    def test_exports_are_repeatable_but_wrong_identity_rejected(self):
        root=Path(__file__).resolve().parents[1]/'artifacts/spx_daily_regime_20261026'
        if not (root/'raw.json').exists():self.skipTest('large native artifact not in checkout')
        a,b=root/'raw.json',root/'reconciliation_raw.json'
        rows,hashes=load_exports(a,b)
        self.assertEqual(len(rows),295)
        self.assertEqual(set(rows[0]),{'date','close'})
        import json
        raw=json.loads(a.read_text());raw['request']['security_type']='FUT'
        with tempfile.TemporaryDirectory() as temp:
            changed=Path(temp)/'changed.json';changed.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError,'wrong native'):load_exports(changed,b)
