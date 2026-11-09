import unittest,tempfile,json,hashlib
from pathlib import Path
import pandas as pd
from replay import closed,insert_events,verified_model
class Tests(unittest.TestCase):
 def test_forming_bar_rejected(self):
  d=pd.DataFrame({'available':pd.to_datetime(['2026-11-03T14:35Z','2026-11-03T14:40Z'],utc=True)});self.assertEqual(len(closed(d,'2026-11-03T14:37Z')),1)
 def test_timezone_required(self):
  with self.assertRaises(ValueError):closed(pd.DataFrame({'available':[]}), '2026-11-03T14:37')
 def test_no_duplicates(self):
  s={'signals':[],'last_slot':None};e=[{'decision_utc':'a','slot':1},{'decision_utc':'b','slot':11}];self.assertEqual(insert_events(s,e),2);self.assertEqual(insert_events(s,e),0)
 def test_cooldown_persists(self):
  s={'signals':[],'last_slot':None};insert_events(s,[{'decision_utc':'a','slot':1}]);self.assertEqual(insert_events(s,[{'decision_utc':'b','slot':5}]),0)
 def test_modified_model_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'model').write_text('{}');(p/'recipe').write_text(json.dumps({'sha256':hashlib.sha256(b'{}').hexdigest()}));verified_model(p/'recipe',p/'model');(p/'model').write_text('{"x":1}')
   with self.assertRaises(ValueError):verified_model(p/'recipe',p/'model')
if __name__=='__main__':unittest.main()
