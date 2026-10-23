import unittest
import pandas as pd
from spx_consensus import directions, features, schedule


class ConsensusTests(unittest.TestCase):
    def setup_frame(self):
        return pd.DataFrame(dict(valid=[True], ambiguous=[False], bar_range=[.3], atr=[1.],
            close=[100.12],prior_high3=[100.2],prior_low3=[99.8],original_direction=[0],
            body=[.12],move3=[.12],previous_close=[100.],position=[.8],slope5=[.2],ema15=[100.]))

    def test_requires_both_conditions_and_never_accepts_break(self):
        frame=self.setup_frame()
        self.assertEqual(directions(frame,'inside_slope_consensus').iloc[0],1)
        for column,value in [('slope5',0.),('original_direction',1),('valid',False),('close',100.3)]:
            altered=frame.copy();altered.loc[0,column]=value
            self.assertEqual(directions(altered,'inside_slope_consensus').iloc[0],0,column)

    def test_downward_symmetry(self):
        frame=self.setup_frame()
        frame.loc[0,['close','body','move3','position','slope5']]=[99.88,-.12,-.12,.2,-.2]
        self.assertEqual(directions(frame,'inside_slope_consensus').iloc[0],-1)

    def bars(self):
        index=pd.date_range('2026-10-22T14:00Z',periods=80,freq='min')
        close=pd.Series([100+i*.15 for i in range(80)],index=index)
        bars=pd.DataFrame(dict(Open=close-.08,High=close+.2,Low=close-.5,Close=close))
        bars.attrs.update(symbol='SPX',security_type='IND')
        return bars

    def test_future_prefix_and_fixed_cooldown(self):
        bars=self.bars();full=schedule(features(bars),'inside_slope_consensus')
        self.assertGreater(len(full),2)
        prefix=schedule(features(bars.iloc[:60]),'inside_slope_consensus')
        self.assertEqual(prefix,[x for x in full if x['index']<60])
        altered=bars.copy();altered.iloc[60:]+=1000
        self.assertEqual(prefix,[x for x in schedule(features(altered),'inside_slope_consensus') if x['index']<60])
        self.assertTrue(all(pd.Timestamp(b['detected_at'])-pd.Timestamp(a['detected_at'])>=pd.Timedelta(minutes=10)
            for a,b in zip(full,full[1:])))
        self.assertTrue(all(not x['notify_eligible'] for x in full))

    def test_price_rescaling_preserves_signals(self):
        bars=self.bars();changed=bars*2+10;changed.attrs.update(bars.attrs)
        self.assertEqual(schedule(features(bars),'inside_slope_consensus'),
                         schedule(features(changed),'inside_slope_consensus'))


if __name__=='__main__':
    unittest.main()
