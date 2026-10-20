import unittest
import tempfile
import json
import hashlib
from pathlib import Path
import halfminute_research as module
import numpy as np
import pandas as pd
from halfminute_research import complete_minutes,prepared,direction,schedule,score,refine_events,verify_protocol,missed_event_audit


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

    def test_refined_onset_removes_artificial_halfminute_early_credit(self):
        index=pd.date_range('2026-10-19T13:30:00Z',periods=8,freq='30s')
        bars=pd.DataFrame({'Open':[100]*8,'High':[100.1,100.1,100.4,100.4,101.2,101.2,101.2,101.2],
                           'Low':[99.9]*8,'Close':[100,100,100.3,100.3,101,101,101,101],
                           'Volume':[100]*8},index=index,dtype=float)
        minute=complete_minutes(bars)
        event={'event_id':0,'anchor_index':0,'target_index':2,'target_points':1.,'direction':1,
               'onset_time':(minute.index[1]+pd.Timedelta(minutes=1)).isoformat()}
        refined=refine_events([event],minute,bars)[0]
        self.assertEqual(pd.Timestamp(refined['onset_time_30s']),pd.Timestamp('2026-10-19T13:31:30Z'))
        self.assertEqual(pd.Timestamp(refined['target_start_30s']),pd.Timestamp('2026-10-19T13:32:00Z'))
        self.assertLess(pd.Timestamp(refined['onset_time_30s']),pd.Timestamp(refined['onset_time']))

    def test_frozen_parameter_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'artifacts/halfminute-pilot'
            target.mkdir(parents=True)
            config=dict(module.CONFIG);config['rvol_half']=1.4
            frozen={'config':config,'methods':list(module.METHODS),
                    'source_sha256':hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
            (target/'frozen.json').write_text(json.dumps(frozen))
            with self.assertRaises(ValueError):verify_protocol(directory)

    def test_miss_audit_identifies_no_completed_observation_before_onset(self):
        anchor=pd.Timestamp('2026-10-19T14:00:00Z')
        event={'event_id':0,'direction':1,'anchor_completed_at':anchor.isoformat(),
               'onset_time_30s':(anchor+pd.Timedelta(seconds=30)).isoformat()}
        rows=[{'generated_at':anchor+pd.Timedelta(seconds=30),'valid':False}]
        result=missed_event_audit([event],rows,{'matches':[]})
        self.assertTrue(result[0]['no_completed_half_before_onset'])

    def test_incomplete_future_is_censored_after_signal_schedule(self):
        bars=data(90);minute=complete_minutes(bars)
        signal={'bar_start':bars.index[-5].isoformat(),'generated_at':(bars.index[-5]+pd.Timedelta(seconds=30)).isoformat(),
                'minute_start':bars.index[-5].floor('min').isoformat(),'direction':1}
        r=score([], [signal], bars, minute,list(range(len(minute))),0)
        self.assertEqual(r['signals'],0);self.assertEqual(r['censored'],1)
