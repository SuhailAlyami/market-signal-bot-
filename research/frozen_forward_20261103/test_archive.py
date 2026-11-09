import unittest,tempfile,json
from pathlib import Path
from stable_archive import merge_archive
class Tests(unittest.TestCase):
 def snapshot(self,p,times,closes=None):
  n=len(times);p.write_text(json.dumps({'chart_step':300,'time':times,'open':[100.]*n,'high':[102.]*n,'low':[99.]*n,'close':closes or [101.]*n,'volume':[10]*n}))
 def test_rolling_snapshot_preserves_history(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:30Z','2026-11-03T14:35Z']);merge_archive(s,a,'2026-11-03T15:00Z');self.snapshot(s,['2026-11-03T14:35Z','2026-11-03T14:40Z']);r=merge_archive(s,a,'2026-11-03T15:00Z');self.assertEqual(r['archive_bars'],3)
 def test_revision_rejected_without_mutation(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:30Z']);merge_archive(s,a,'2026-11-03T15:00Z');b=a.read_bytes();self.snapshot(s,['2026-11-03T14:30Z'],[100.5])
   with self.assertRaises(ValueError):merge_archive(s,a,'2026-11-03T15:00Z')
   self.assertEqual(b,a.read_bytes())
 def test_forming_excluded_then_saved(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:30Z']);r=merge_archive(s,a,'2026-11-03T14:33Z');self.assertEqual(r['archive_bars'],0);r=merge_archive(s,a,'2026-11-03T14:35Z');self.assertEqual(r['archive_bars'],1)
 def test_repeated_snapshot_no_new_rows(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:30Z']);merge_archive(s,a,'2026-11-03T15:00Z');self.assertEqual(merge_archive(s,a,'2026-11-03T15:00Z')['newly_preserved_bars'],0)
 def test_backdated_asof_never_deletes_archive(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:30Z','2026-11-03T14:35Z']);merge_archive(s,a,'2026-11-03T15:00Z');r=merge_archive(s,a,'2026-11-03T14:33Z');self.assertEqual(r['archive_bars'],2)
 def test_no_fabricated_spx_volume(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:30Z']);r=json.loads(s.read_text());r.pop('volume');s.write_text(json.dumps(r));merge_archive(s,a,'2026-11-03T15:00Z');self.assertNotIn('volume',json.loads(a.read_text()))
 def test_backfill_does_not_change_historical_features(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);s=p/'s';a=p/'a';self.snapshot(s,['2026-11-03T14:35Z']);merge_archive(s,a,'2026-11-03T15:00Z');old=a.read_bytes();self.snapshot(s,['2026-11-03T14:30Z','2026-11-03T14:35Z'])
   with self.assertRaises(ValueError):merge_archive(s,a,'2026-11-03T15:00Z')
   self.assertEqual(old,a.read_bytes())
if __name__=='__main__':unittest.main()
