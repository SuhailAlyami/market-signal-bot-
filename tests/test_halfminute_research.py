import unittest
import numpy as np
import pandas as pd
from halfminute_research import complete_minutes,prepared,direction,schedule,score


def data(n=160):
    index=pd.date_range('2026-10-19T13:00:00Z',periods=n,freq='30s')
    close=100+np.sin(np.arange(n)/8)*.1
    return pd.DataFrame({'Open':close-.01,'High':close+.02,'Low':close-.02,'Close':close,'Volume':100.},index=index)


class HalfMinuteTests(unittest.TestCase):
    def test_aggregation_requires_both_real_halves(self):
        bars=data(5)
        minute=complete_minutes(bars)
        self.assertEqual(len(minute),2)
        self.assertEqual(len(complete_minutes(bars.drop(bars.index[1]))),1)
        self.assertEqual(minute.Volume.iloc[0],200.)

    def test_prefix_features_do_not_see_second_half_or_future_minutes(self):
        bars=data();other=bars.copy()
        expected=prepared(bars.iloc[:101],other.iloc[:101])[2][-1]
        bars.iloc[101:]=[500.,510.,490.,505.,100000.]
        other.iloc[101:]=[500.,510.,490.,505.,100000.]
        actual=prepared(bars,other)[2][100]
        self.assertEqual(expected,actual)

    def test_missing_counterpart_half_blocks_confirmation(self):
        bars=data();other=bars.drop(bars.index[100])
        row=prepared(bars,other)[2][100]
        self.assertFalse(row['valid'])

    def test_opposing_counterpart_and_invalid_history_block_setup(self):
        row={'valid':True,'rvol':2.,'trend':1.,'other_move':.5,'high_level':100.1,'low_level':99.,
             'close':100.,'atr':1.,'contraction':.4,'move':.2}
        self.assertEqual(direction(row,'half_setup'),1)
        row['other_move']=-.5
        self.assertEqual(direction(row,'half_setup'),0)
        row['valid']=False
        self.assertEqual(direction(row,'half_setup'),0)

    def test_delayed_delivery_cannot_create_event_eligibility(self):
        bars=data(100);minute=complete_minutes(bars)
        signal={'bar_start':bars.index[60].isoformat(),'generated_at':(bars.index[60]+pd.Timedelta(seconds=30)).isoformat(),
                'minute_start':bars.index[60].floor('min').isoformat(),'direction':1}
        event={'event_id':0,'anchor_index':31,'target_index':35,'onset_time':minute.index[34].isoformat(),'direction':1}
        for delay in (0,60,120):
            r=score([event],[signal],bars,minute,list(range(len(minute))),delay)
            self.assertEqual(r['matched'],0)

    def test_incomplete_future_is_censored_after_signal_schedule(self):
        bars=data(90);minute=complete_minutes(bars)
        signal={'bar_start':bars.index[-5].isoformat(),'generated_at':(bars.index[-5]+pd.Timedelta(seconds=30)).isoformat(),
                'minute_start':bars.index[-5].floor('min').isoformat(),'direction':1}
        r=score([], [signal], bars, minute,list(range(len(minute))),0)
        self.assertEqual(r['signals'],0);self.assertEqual(r['censored'],1)
