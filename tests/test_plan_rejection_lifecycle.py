import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from hunter_runtime import HunterRuntime


class RejectionLifecycleTests(unittest.TestCase):
    def runtime(self,directory):
        detector=lambda data,i:dict(direction=1,price=data.Close.iloc[i],atr=1.,level=100.,invalidation=98.,rvol=1.5)
        return HunterRuntime(Path(directory)/'state.json',Path(directory)/'journal.jsonl',symbols=('ES=F',),detector=detector)

    def trigger(self,runtime,begin='2026-09-02T14:00Z'):
        bars=pd.DataFrame(dict(Open=[99.9,100.1,100.2],High=[100.,100.4,100.5],Low=[99.,100.,100.],Close=[99.9,100.3,100.4],Volume=100.),index=pd.date_range(begin,periods=3,freq='min'))
        events=[]
        with patch('price_action_context.observe',return_value={'status':'fixture'}):
            for i,t in enumerate(bars.index):events+=runtime._process_bar('ES=F',bars,i,(t+pd.Timedelta(minutes=1)).to_pydatetime())
        return bars,next(e for e in events if e['state']=='TRIGGER')

    def test_rejection_releases_next_bar_but_preserves_dedupe_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(directory);bars,event=self.trigger(runtime)
            self.assertTrue(runtime.reject_plan(event,'risk_or_entry_invalid'))
            restored=self.runtime(directory)
            self.assertNotIn('active',restored.state['symbols']['ES=F'])
            with patch('price_action_context.observe',return_value={'status':'fixture'}):
                self.assertEqual(restored._process_bar('ES=F',bars,2,pd.Timestamp(event['bar_end']).to_pydatetime()),[])
                future=bars.copy();future.index+=pd.Timedelta(minutes=3)
                new=restored._process_bar('ES=F',future,0,(future.index[0]+pd.Timedelta(minutes=1)).to_pydatetime())
            self.assertEqual(new[0]['state'],'SETUP')
            self.assertNotIn('cooldown_until',restored.state['symbols']['ES=F'])

    def test_late_rejection_cannot_clear_newer_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(directory);_,old=self.trigger(runtime)
            self.assertTrue(runtime.reject_plan(old,'rejected'))
            _,new=self.trigger(runtime,'2026-09-02T14:05Z')
            self.assertFalse(runtime.reject_plan(old,'late_response'))
            self.assertEqual(runtime.state['symbols']['ES=F']['active']['phase'],'TRIGGER')
            self.assertTrue(runtime.reject_plan(new,'rejected'))

    def test_persistence_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(directory);_,event=self.trigger(runtime)
            with patch.object(runtime,'_save',side_effect=OSError('disk unavailable')):
                self.assertFalse(runtime.reject_plan(event,'rejected'))
            self.assertEqual(runtime.persistence_error,'persistence_failed')


if __name__=='__main__':unittest.main()
