import unittest
from unittest.mock import patch
import pandas as pd
from intrabar_sweep import detect


class CarryTests(unittest.TestCase):
    def fixture(self):
        raw=pd.DataFrame(dict(Open=101.,High=101.05,Low=100.95,Close=101.,Volume=10.),
            index=pd.date_range('2026-09-02T14:00Z',periods=180,freq='5s'))
        raw.iloc[23]=[100.2,100.25,99.8,99.9,10.]
        raw.iloc[24]=[100.2,100.5,100.15,100.4,20.]
        raw.iloc[25]=[100.4,100.65,100.35,100.6,30.]
        def contexts(minute):
            f=pd.DataFrame(dict(valid=True,contraction=.5,atr=1.,low5=100.,high5=102.),index=minute.index)
            # New context differs; carry must retain the known ORIGINAL range.
            f.loc[f.index>=pd.Timestamp('2026-09-02T14:01Z'),'low5']=99.
            return f
        return raw,contexts

    def test_cross_minute_sequence_uses_original_context_and_real_extreme(self):
        raw,contexts=self.fixture()
        with patch('intrabar_sweep.context_frame',side_effect=contexts):
            self.assertEqual(detect(raw)[1],[])
            plans=detect(raw,carry_sweep=True)[1]
        self.assertEqual(len(plans),1)
        self.assertEqual(plans[0]['detected_at'],'2026-09-02T14:02:10+00:00')
        self.assertEqual(plans[0]['context_bar'],'2026-09-02T14:00:00+00:00')
        self.assertEqual(plans[0]['stop_loss'],99.5)

    def test_gap_invalidates_unfinished_sweep(self):
        raw,contexts=self.fixture();raw=raw.drop(raw.index[24])
        with patch('intrabar_sweep.context_frame',side_effect=contexts):
            self.assertEqual(detect(raw,carry_sweep=True)[1],[])

    def test_future_data_does_not_change_already_detected_plan(self):
        raw,contexts=self.fixture()
        with patch('intrabar_sweep.context_frame',side_effect=contexts):
            first=detect(raw.iloc[:26],carry_sweep=True)[1]
            raw.iloc[30:]=[900.,910.,890.,905.,1000.]
            later=detect(raw,carry_sweep=True)[1]
        self.assertEqual(first,later[:len(first)])

    def test_timeout_does_not_keep_old_sweep_alive(self):
        raw,contexts=self.fixture()
        raw.iloc[24:]=[100.,100.05,99.95,100.,10.]
        raw.iloc[150]=[100.2,100.5,100.15,100.4,20.]
        raw.iloc[151]=[100.4,100.65,100.35,100.6,30.]
        with patch('intrabar_sweep.context_frame',side_effect=contexts):
            self.assertEqual(detect(raw,carry_sweep=True)[1],[])


if __name__=='__main__':unittest.main()
