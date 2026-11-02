import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from recover_spx_archive import recover
class RecoveryTests(unittest.TestCase):
 def fixture(self,root):
  d=b'{"history":{"close":[100]}}';p=root/'2026-07-20.raw.json';p.write_bytes(d);m=root/'manifest.json';m.write_text(json.dumps({'sessions':[{'date':'2026-07-20','raw_sha256':hashlib.sha256(d).hexdigest()}]}));return p,m
 def test_exact_bytes_only(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);p,m=self.fixture(r);z=r/'pack.zip';before=p.read_bytes();a=recover(r,m,z);self.assertTrue(a['packaged']);self.assertEqual(p.read_bytes(),before)
   with zipfile.ZipFile(z) as f:self.assertEqual(f.read(p.name),before)
 def test_bad_hash_does_not_package(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);p,m=self.fixture(r);p.write_bytes(b'wrong');a=recover(r,m,r/'pack.zip');self.assertFalse(a['packaged']);self.assertFalse((r/'pack.zip').exists())
 def test_existing_archive_preserved(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);p,m=self.fixture(r);z=r/'pack.zip';z.write_bytes(b'keep')
   with self.assertRaises(FileExistsError):recover(r,m,z)
   self.assertEqual(z.read_bytes(),b'keep')
if __name__=='__main__':unittest.main()
