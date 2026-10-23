import unittest
import numpy as np
import pandas as pd
from linear_onset_forecast import feature_matrix,training_labels,fit,warnings,NAMES


class ForecastTests(unittest.TestCase):
    def frame(self,n=70):
        prices=100+np.arange(n)*.1
        return pd.DataFrame(dict(Open=prices,High=prices+.4,Low=prices-.3,Close=prices+.1,Volume=100.),
            index=pd.date_range('2026-09-02T14:00Z',periods=n,freq='min'))

    def test_future_mutation_cannot_change_current_features(self):
        bars=self.frame();before=feature_matrix(bars.iloc[:50])
        bars.iloc[50:]=[500.,600.,400.,550.,1000.]
        pd.testing.assert_frame_equal(before,feature_matrix(bars).iloc[:50])

    def test_labels_require_one_minute_real_lead_and_existing_anchor(self):
        bars=self.frame();event=dict(anchor_index=30,target_index=39,direction=1,onset_time='2026-09-02T14:35:00Z')
        y,keep=training_labels(bars,list(range(28,38)),[event])
        self.assertEqual(y.tolist(),[0,0,0,1,1,1,0,0,0,0])
        self.assertTrue(keep.all())

    def test_scaling_uses_only_registered_training_rows(self):
        bars=self.frame(160);f=feature_matrix(bars)
        # Synthetic supervised rows test fitting boundaries, not market quality.
        f.loc[:,'valid']=True
        for k,name in enumerate(NAMES):f[name]=np.arange(len(f))*.01+k
        indices=list(range(120));labels=np.array([0,1,2]*40);keep=np.ones(120,dtype=bool)
        first=fit(f,indices,labels,keep)
        f.loc[f.index[120:],NAMES]=1e8
        self.assertEqual(first,fit(f,indices,labels,keep))

    def test_forecast_warns_without_any_breakout_and_dedupes_regime(self):
        bars=self.frame(5);f=pd.DataFrame(0.,index=bars.index,columns=NAMES);f['valid']=True
        weights=np.zeros((9,3));weights[0,1]=5
        model=dict(center=[0.]*8,scale=[1.]*8,weights=weights.tolist())
        signals=warnings(bars,f,model,list(range(5)))
        self.assertEqual(len(signals),1)
        self.assertEqual(signals[0]['detected_at'],'2026-09-02T14:01:00+00:00')
        self.assertEqual(signals[0]['state'],'WATCH')
        self.assertFalse(signals[0]['notify_eligible'])


if __name__=='__main__':unittest.main()
