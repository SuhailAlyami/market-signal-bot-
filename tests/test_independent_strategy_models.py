import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd

from acquire_independent_history import HistoryClient
from independent_strategy_models import reversal_candidate,continuation_confirmation,common_risk_plan
from es_signal_plan import complete_plan
from validate_independent_reversal import absolute_gate


class IndependentTests(unittest.TestCase):
    def test_reversal_can_confirm_against_old_trend_but_not_without_delivery_shift(self):
        f=dict(valid=True,contraction=.5,rvol=1.5,range_low=99.,range_high=101.,atr=2.,close=100.,
               trend_5=-2.,trend_15=-3.,move=.5)
        row=pd.Series(dict(Open=99.,Close=100.,Low=98.5,High=100.5))
        previous=pd.Series(dict(Open=99.5,Close=99.))
        self.assertFalse(continuation_confirmation(f,1))
        found=reversal_candidate(f,row,previous)
        self.assertEqual(found['direction'],1)
        self.assertIsNotNone(common_risk_plan({'direction':'UP','invalidation':found['invalidation']},f)[0])
        previous.Open=100.25
        self.assertIsNone(reversal_candidate(f,row,previous))

    def test_common_risk_exactly_matches_production_without_strategy_filters(self):
        frame=pd.DataFrame(index=pd.date_range('2026-10-22T03:00Z',periods=32,freq='min'))
        for side in (1,-1):
            f=dict(atr=2.,close=100.,rvol=1.5,trend_5=side,trend_15=side,move=side)
            event=dict(symbol='ES=F',state='TRIGGER',direction='UP' if side>0 else 'DOWN',
                       invalidation=98.5 if side>0 else 101.5,bar_end='2026-10-22T03:32:00+00:00')
            with patch('es_signal_plan.causal_features',return_value=f):
                production,reason=complete_plan(event,frame)
            common,error=common_risk_plan(event,{'atr':2.,'close':100.})
            self.assertIsNone(reason);self.assertIsNone(error)
            for key in ('entry_zone','stop_loss','targets','plan_atr'):self.assertEqual(common[key],production[key])
            self.assertIsNone(common_risk_plan({**event,'invalidation':80. if side>0 else 120.},f)[0])

    def test_historical_capture_does_not_inherit_live_180_row_truncation(self):
        client=HistoryClient()
        for i in range(400):
            client.historicalData(301,SimpleNamespace(date=str(i),open=100.,high=101.,low=99.,close=100.,volume=30.))
        self.assertEqual(len(client.history[301]),400)
        self.assertEqual(len(client.rows),0)

    def test_baseline_has_to_meet_absolute_quality_not_just_beat_failure(self):
        metrics=dict(sessions=10,signals=40,precision=.7,precision_wilson_95=[.5,.8],
            early_event_recall=.25,false_alarms_per_session=1.,median_lead_minutes=2.)
        self.assertTrue(absolute_gate(metrics))
        self.assertFalse(absolute_gate({**metrics,'signals':1}))
        self.assertFalse(absolute_gate({**metrics,'early_event_recall':.01}))
        self.assertFalse(absolute_gate({**metrics,'precision_wilson_95':[.2,.8]}))


if __name__=='__main__':unittest.main()
