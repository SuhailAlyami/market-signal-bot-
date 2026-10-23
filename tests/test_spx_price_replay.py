import json
from pathlib import Path
import tempfile
import unittest

from replay_spx_price_watch import replay


class ReplayTests(unittest.TestCase):
    def test_native_index_replay_needs_no_volume_and_drops_received_partial(self):
        import pandas as pd
        times=pd.date_range('2026-10-22T13:30Z',periods=46,freq='min')
        raw={'contract':{'symbol':'SPX','country_code':'US','underlying_contract_id':1,
                         'sections':[{'security_type':'IND'}]},
             'received_at':'2026-10-22T14:15:30Z',
             'history':{'chart_end':'2026-10-22T20:00:00Z','time':[t.isoformat() for t in times],
                        'open':[100.]*46,'high':[100.2]*46,'low':[99.8]*46,'close':[100.]*46}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'raw.json';out=Path(directory)/'result.json'
            path.write_text(json.dumps(raw))
            result=replay(path,out,'fixed-before-test')
            self.assertEqual(result['bars'],45)
            self.assertEqual(result['excluded_partial_bars'],1)
            self.assertEqual(result['completion_cutoff'],'2026-10-22T14:15:30+00:00')
            self.assertFalse(result['holdout'])
            self.assertFalse(result['accepted'])
            self.assertFalse(result['notifications_enabled'])
            self.assertEqual(result['metrics']['watch']['signals'],0)


if __name__=='__main__':
    unittest.main()
