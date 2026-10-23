import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
from tests.test_spx_research_agent import w


class HostCheckpointTests(unittest.TestCase):
    def fake(self, status):
        def git(root,*args):
            return subprocess.CompletedProcess(args,1 if args[0]=='ls-files' else 0,
                stdout=status if args[0]=='status' else '',stderr='')
        return git

    def test_only_explicit_research_paths_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'docs').mkdir();(root/'RESUME.md').write_text('checkpoint')
            (root/'docs/new.md').write_text('measured result')
            paths=['RESUME.md','docs/new.md']
            with patch.object(w,'git',side_effect=self.fake(' M RESUME.md\0?? docs/new.md\0')) as calls:
                w.commit_checkpoint(root,paths)
            staged=[c.args[1:] for c in calls.call_args_list if c.args[1]=='add']
            self.assertEqual(staged,[('add','--',*paths)])

    def test_unlisted_change_blocks_before_staging(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'git',side_effect=self.fake(' M RESUME.md\0?? extra.py\0')) as calls:
            with self.assertRaisesRegex(RuntimeError,'manifest_mismatch'):
                w.commit_checkpoint(Path(tmp),['RESUME.md'])
            self.assertFalse(any(c.args[1]=='add' for c in calls.call_args_list))

    def test_private_raw_production_and_traversal_are_rejected(self):
        for name in ['artifacts/raw.json','artifacts/2026-10-19.raw.json','hunter_runtime.py','docs/AGENTS.md','../outside.md']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                if '..' not in name:
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('not publishable')
                with patch.object(w,'git',side_effect=self.fake('?? '+name+'\0')) as calls:
                    with self.assertRaises(RuntimeError):w.commit_checkpoint(root,[name])
                    self.assertFalse(any(c.args[1]=='add' for c in calls.call_args_list))

    def test_daily_collector_raw_wakes_but_derived_reports_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'.hunter-state/capture';folder.mkdir(parents=True)
            before=w.fingerprint(root)
            (folder/'2026-10-19.validated.json').write_text('{}')
            self.assertEqual(before,w.fingerprint(root))
            (folder/'2026-10-19.raw.json').write_text('{"rows":[1]}')
            self.assertNotEqual(before,w.fingerprint(root))

    def test_deletion_never_staged(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'git',side_effect=self.fake(' D docs/old.md\0')):
            with self.assertRaisesRegex(RuntimeError,'rename_or_delete'):w.commit_checkpoint(Path(tmp),['docs/old.md'])


if __name__=='__main__':unittest.main()
