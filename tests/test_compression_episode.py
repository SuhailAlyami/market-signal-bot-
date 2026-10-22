import unittest
from unittest.mock import patch
import pandas as pd
from preaccel_warning import detect


class EpisodeTests(unittest.TestCase):
    def fixture(self):
        raw=pd.DataFrame(dict(Open=101.,High=101.05,Low=100.95,Close=101.,Volume=10.),
            index=pd.date_range('2026-09-02T14:00Z',periods=60,freq='5s'))
        def contexts(minute):
            return pd.DataFrame(dict(valid=True,contraction=.5,atr=1.,low5=100.,high5=102.,trend5=.5),index=minute.index)
        return raw,contexts

    def test_warns_at_formation_without_waiting_for_volume_or_near_edge(self):
        raw,contexts=self.fixture()
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            _,warnings,entries,_=detect(raw,mode='episode')
        self.assertEqual(len(warnings),1)
        self.assertEqual(warnings[0]['detected_at'],'2026-09-02T14:01:05+00:00')
        self.assertEqual(warnings[0]['rvol'],1.)
        self.assertEqual(entries,[])

    def test_range_changes_do_not_rearm_but_new_compression_does(self):
        raw,base=self.fixture()
        def contexts(minute):
            f=base(minute);f['high5']+=pd.Series(range(len(f)),index=f.index)*.1
            f.loc[pd.Timestamp('2026-09-02T14:02Z'),'contraction']=.8
            return f
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            warnings=detect(raw,mode='episode')[1]
        self.assertEqual(len(warnings),2)
        self.assertEqual(warnings[1]['detected_at'],'2026-09-02T14:04:05+00:00')

    def test_preexisting_breach_cannot_be_called_early_warning(self):
        raw,contexts=self.fixture();raw.iloc[12]=[102.2,102.4,102.1,102.3,10.]
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            self.assertEqual(detect(raw,mode='episode')[1],[])


if __name__=='__main__':unittest.main()
