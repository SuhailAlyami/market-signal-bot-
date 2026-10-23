import unittest
from unittest.mock import patch
import pandas as pd
from preaccel_warning import detect


class WarningTests(unittest.TestCase):
    def fixture(self,stop=100.):
        raw=pd.DataFrame(dict(Open=101.,High=101.05,Low=100.95,Close=101.,Volume=10.),
            index=pd.date_range('2026-09-02T14:00Z',periods=42,freq='5s'))
        raw.iloc[14]=[101.7,101.95,101.65,101.9,30.]
        raw.iloc[15]=[101.9,102.3,101.85,102.2,30.]
        raw.iloc[16]=[102.2,102.5,102.15,102.4,30.]
        raw.iloc[25]=[102.2,102.45,102.15,102.4,30.]
        def contexts(minute):
            f=pd.DataFrame(dict(valid=True,contraction=.5,atr=1.,low5=stop,high5=102.,trend5=.5),index=minute.index)
            f.loc[f.index>=pd.Timestamp('2026-09-02T14:01Z'),'high5']=102.5
            return f
        return raw,contexts

    def test_watch_precedes_breach_and_entry_is_separate(self):
        raw,contexts=self.fixture(stop=101.2)
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            _,warnings,entries,_=detect(raw)
        self.assertEqual(warnings[0]['detected_at'],'2026-09-02T14:01:15+00:00')
        self.assertLess(warnings[0]['price'],warnings[0]['level'])
        self.assertFalse(warnings[0]['entry_confirmed'])
        self.assertEqual(entries[0]['detected_at'],'2026-09-02T14:01:25+00:00')
        self.assertEqual(entries[0]['watch_id'],warnings[0]['watch_id'])

    def test_rejected_entry_cannot_hide_new_warning(self):
        raw,contexts=self.fixture()
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            _,warnings,entries,diag=detect(raw)
        self.assertEqual(len(warnings),2)
        self.assertEqual(entries,[])
        self.assertGreaterEqual(diag['entry_rejected_risk_or_entry_invalid'],1)
        self.assertNotEqual(warnings[0]['level'],warnings[1]['level'])

    def test_future_mutation_does_not_rewrite_warning(self):
        raw,contexts=self.fixture()
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            old=detect(raw.iloc[:15])[1]
            raw.iloc[20:]=[800.,810.,790.,805.,1000.]
            new=detect(raw)[1]
        self.assertEqual(old,new[:len(old)])

    def test_zero_volume_or_missing_bar_cannot_create_warning(self):
        raw,contexts=self.fixture();raw.iloc[14,raw.columns.get_loc('Volume')]=0
        raw=raw.drop(raw.index[24])
        with patch('preaccel_warning.context_frame',side_effect=contexts):
            self.assertEqual(detect(raw)[1],[])


if __name__=='__main__':unittest.main()
