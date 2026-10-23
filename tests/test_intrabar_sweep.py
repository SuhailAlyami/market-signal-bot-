import unittest
from unittest.mock import patch
import pandas as pd
from intrabar_sweep import detect


class SweepSequenceTests(unittest.TestCase):
    def fixture(self):
        raw=pd.DataFrame(dict(Open=101.,High=101.05,Low=100.95,Close=101.,Volume=10.),
            index=pd.date_range('2026-09-02T14:00Z',periods=36,freq='5s'))
        raw.iloc[14]=[100.2,100.25,99.8,99.9,10.]
        raw.iloc[15]=[100.2,100.5,100.15,100.4,20.]
        raw.iloc[16]=[100.4,100.65,100.35,100.6,30.]
        def contexts(minute):
            return pd.DataFrame(dict(valid=True,contraction=.5,atr=1.,low5=100.,high5=102.),index=minute.index)
        return raw,contexts

    def test_sweep_then_two_later_real_closes_with_actual_wick_stop(self):
        raw,contexts=self.fixture()
        with patch('intrabar_sweep.context_frame',side_effect=contexts):
            _,plans,_=detect(raw)
        self.assertEqual(len(plans),1)
        self.assertEqual(plans[0]['detected_at'],'2026-09-02T14:01:25+00:00')
        self.assertEqual(plans[0]['stop_loss'],99.5)  # outward rounded99.8-.25

    def test_double_sweep_or_nontrading_confirmation_cannot_publish(self):
        raw,contexts=self.fixture();raw.iloc[14,raw.columns.get_loc('High')]=102.2
        with patch('intrabar_sweep.context_frame',side_effect=contexts):self.assertEqual(detect(raw)[1],[])
        raw,contexts=self.fixture();raw.iloc[16,raw.columns.get_loc('Volume')]=0
        with patch('intrabar_sweep.context_frame',side_effect=contexts):self.assertEqual(detect(raw)[1],[])


if __name__=='__main__':unittest.main()
