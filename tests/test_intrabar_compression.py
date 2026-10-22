import unittest
import pandas as pd
from intrabar_compression import minute_frame,context_positions,refine_events


class TimingTests(unittest.TestCase):
    def bars(self):
        return pd.DataFrame(dict(Open=100.,High=100.1,Low=99.9,Close=100.,Volume=10.),
            index=pd.date_range('2026-09-02T14:00Z',periods=36,freq='5s'))

    def test_cannot_use_minute_finished_at_same_five_second_close(self):
        raw=self.bars();minute=minute_frame(raw)
        indices=pd.DatetimeIndex(['2026-09-02T14:00:55Z','2026-09-02T14:01:00Z'])
        self.assertEqual(context_positions(minute,indices).tolist(),[-1,0])

    def test_missing_observation_is_not_filled_or_averaged_into_valid_minute(self):
        raw=self.bars().drop(pd.Timestamp('2026-09-02T14:00:25Z'))
        minute=minute_frame(raw)
        self.assertTrue(minute.iloc[0].isna().all())
        self.assertEqual(minute.iloc[1].Volume,120.)
        with self.assertRaises(ValueError):minute_frame(pd.concat([raw,raw.iloc[-1:]]))

    def test_refined_onset_uses_earliest_possible_touch_not_minute_close(self):
        raw=self.bars();minute=minute_frame(raw)
        raw.loc[pd.Timestamp('2026-09-02T14:01:10Z'),'High']=100.6
        raw.loc[pd.Timestamp('2026-09-02T14:01:30Z'),'High']=102.1
        event=dict(anchor_index=0,end_index=2,target_index=1,direction=1,target_points=2.,
            onset_time='2026-09-02T14:02:00+00:00',target_time='2026-09-02T14:02:00+00:00')
        result=refine_events([event],minute,raw)[0]
        self.assertEqual(result['onset_time'],'2026-09-02T14:01:10+00:00')
        self.assertEqual(result['coarse_onset_time'],event['onset_time'])
        self.assertEqual(event['onset_time'],'2026-09-02T14:02:00+00:00')


if __name__=='__main__':unittest.main()
