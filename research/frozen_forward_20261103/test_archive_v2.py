import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import archive_v2 as v

class Tests(unittest.TestCase):
    def snap(self, path, times, closes=None):
        n=len(times)
        path.write_text(json.dumps(dict(chart_step=300,time=times,open=[100]*n,
            high=[103]*n,low=[99]*n,close=closes or [101]*n,volume=[10]*n)))

    def setup_files(self, p):
        seed=p/'seed'; seed.mkdir()
        for sym in ['SPX','ES']:
            self.snap(seed/(sym+'_archive.json'),['2026-11-03T14:30Z'])
        (seed/'ARCHIVE_STATE.json').write_text('{"signals":[]}')
        sp=p/'sp.json'; es=p/'es.json'
        for x in [sp,es]:self.snap(x,['2026-11-03T14:30Z','2026-11-03T14:35Z'],[100.5,102])
        return seed,sp,es

    def fake(self, sp, es, asof, state, output):
        output.write_text('{"status":"test"}')
        return {'status':'test'}

    def test_first_values_preserved_and_revisions_logged(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p);before=(seed/'SPX_archive.json').read_bytes()
            with patch.object(v,'P',seed):v.run(sp,es,'2026-11-03T15:00Z',p/'v2',self.fake)
            cp=v.previous(p/'v2');r=json.loads((cp/'SPX_archive.json').read_text())
            self.assertEqual(r['close'],[101,102]);self.assertEqual(before,(seed/'SPX_archive.json').read_bytes())
            self.assertEqual(json.loads((cp/'SPX_REVISIONS.json').read_text())['revision_count'],1)

    def test_second_feed_failure_never_advances_pair(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p)
            with patch.object(v,'P',seed):
                v.run(sp,es,'2026-11-03T15:00Z',p/'v2',self.fake)
                pointer=(p/'v2/CURRENT').read_bytes()
                self.snap(sp,['2026-11-03T14:40Z'])
                b=json.loads(es.read_text());b['high'][0]=1;es.write_text(json.dumps(b))
                with self.assertRaises(ValueError):v.run(sp,es,'2026-11-03T15:05Z',p/'v2',self.fake)
                self.assertEqual(pointer,(p/'v2/CURRENT').read_bytes())
                self.assertEqual(len(json.loads((v.previous(p/'v2')/'SPX_archive.json').read_text())['time']),2)

    def test_evaluation_failure_does_not_publish(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p)
            def fail(*args):raise RuntimeError('evaluation failed')
            with patch.object(v,'P',seed):
                with self.assertRaises(RuntimeError):v.run(sp,es,'2026-11-03T15:00Z',p/'v2',fail)
            self.assertFalse((p/'v2/CURRENT').exists())

    def test_replay_repeat_and_checksum_guard(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p)
            with patch.object(v,'P',seed):
                v.run(sp,es,'2026-11-03T15:00Z',p/'v2',self.fake)
                r=v.run(sp,es,'2026-11-03T15:01Z',p/'v2',self.fake)
                self.assertEqual(r['archive']['SPX']['newly_preserved_bars'],0)
                (v.previous(p/'v2')/'ARCHIVE_STATE.json').write_text('{}')
                with self.assertRaises(ValueError):v.run(sp,es,'2026-11-03T15:02Z',p/'v2',self.fake)

    def test_calendar_accepts_next_session_without_reindexing_past(self):
        import pandas as pd
        from replay import base
        d=pd.DataFrame(dict(ts=pd.to_datetime(['2026-11-03T14:30Z','2026-11-04T14:30Z']),
            open=[100.,100.],high=[102.,102.],low=[99.,99.],close=[101.,101.],volume=[1.,1.]))
        old,_=base.prepare(d.iloc[:1],d.iloc[:1],5)
        new,_=base.prepare(d,d,5)
        self.assertEqual(len(new),2)
        self.assertEqual(old.slot.iloc[0],new.slot.iloc[0])

    def test_delayed_provider_blocks_fresh_delivery_without_blocking_archive(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p)
            for path,delay in [(sp,900),(es,600)]:
                data=json.loads(path.read_text());data['delayed']=delay;data['source']='Last'
                path.write_text(json.dumps(data))
            with patch.object(v,'P',seed):
                result=v.run(sp,es,'2026-11-03T14:41Z',p/'v2',self.fake)
            quality=result['archive']['delivery_readiness']
            self.assertFalse(quality['eligible_for_fresh_signal_check'])
            self.assertIn('SPX_PROVIDER_DELAY_EXCEEDS_180_SECONDS',quality['reasons'])
            self.assertEqual(quality['feeds']['SPX']['closed_bar_age_seconds'],60)
            self.assertTrue((v.previous(p/'v2')/'ARCHIVE_RESULT.json').exists())

    def test_fresh_common_closed_bar_and_actual_age(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p)
            for path in [sp,es]:
                data=json.loads(path.read_text());data['delayed']=0
                path.write_text(json.dumps(data))
            self.assertTrue(v.delivery_readiness(sp,es,'2026-11-03T14:41Z')['eligible_for_fresh_signal_check'])
            self.assertFalse(v.delivery_readiness(sp,es,'2026-11-03T14:44Z')['eligible_for_fresh_signal_check'])
            self.snap(es,['2026-11-03T14:30Z','2026-11-03T14:40Z'])
            quality=v.delivery_readiness(sp,es,'2026-11-03T14:41Z')
            self.assertEqual(quality['feeds']['ES']['last_closed_Riyadh'],'2026-11-03 17:35:00+03:00')
            self.assertIn('COMMON_CLOSED_BAR_OUTSIDE_180_SECONDS',quality['reasons'])

    def test_shadow_and_notification_ledger_survive_normal_resume(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);seed,sp,es=self.setup_files(p)
            saved={'GROK_SHADOW.json':b'{"events":[]}',
                   'OUTCOME_NOTIFICATIONS.json':b'{"reported_in_chat":["existing"]}'}
            for name,content in saved.items():(seed/name).write_bytes(content)
            with patch.object(v,'P',seed):
                v.run(sp,es,'2026-11-03T15:00Z',p/'v2',self.fake)
                v.run(sp,es,'2026-11-03T15:01Z',p/'v2',self.fake)
            cp=v.previous(p/'v2');manifest=json.loads((cp/'MANIFEST.json').read_text())
            for name,content in saved.items():
                self.assertEqual((cp/name).read_bytes(),content)
                self.assertEqual(manifest['sha256'][name],v.digest(cp/name))

if __name__=='__main__':unittest.main()
