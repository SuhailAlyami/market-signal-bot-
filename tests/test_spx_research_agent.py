import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('worker', Path(__file__).resolve().parents[1] / 'tools/spx_research_agent.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class ResearchWorkerTests(unittest.TestCase):
    def test_gateway_notice_deduplicated_across_ticks_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            w.save(state/'state.json', {'status':'WAIT_DATA','needs_gateway':True,'calls':1})
            sender = unittest.mock.Mock(return_value=True)
            self.assertEqual(w.publish_attention(state,sender),'popup_requested')
            self.assertEqual(w.publish_attention(state,sender),'deduplicated')
            sender.assert_called_once()
            self.assertIn('IB Gateway',(state/'attention.txt').read_text(encoding='utf-8'))
            self.assertEqual(w.json.loads((state/'state.json').read_text())['calls'],1)

    def test_generic_wait_does_not_invent_gateway_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            w.save(state/'state.json',{'status':'WAIT_DATA','summary':'FROZEN before opening'})
            sender = unittest.mock.Mock(return_value=True)
            w.publish_attention(state,sender)
            message = sender.call_args.args[1]
            self.assertIn('لم يتأكد',message)
            self.assertEqual(w.json.loads((state/'attention.json').read_text())['kind'],'data')
            w.save(state/'state.json',{'status':'NOT_READY','needs_gateway':False})
            self.assertEqual(w.publish_attention(state,sender),'no_attention')
            self.assertEqual(sender.call_count,1)

    def test_recovery_allows_same_requirement_to_notify_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            sender = unittest.mock.Mock(return_value=True)
            for status in ('WAIT_DATA','CONTINUE','WAIT_DATA'):
                w.save(state/'state.json',{'status':status,'needs_gateway':True})
                w.publish_attention(state,sender)
            self.assertEqual(sender.call_count,2)

    def test_popup_failure_keeps_fallback_and_retries_after_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            w.save(state/'state.json',{'status':'WAIT_DATA','needs_gateway':True})
            sender = unittest.mock.Mock(return_value=False)
            now = datetime.now(timezone.utc)
            self.assertEqual(w.publish_attention(state,sender,now),'saved_text_only')
            self.assertTrue((state/'attention.txt').exists())
            self.assertEqual(w.publish_attention(state,sender,now+w.timedelta(minutes=15)),'deduplicated')
            w.publish_attention(state,sender,now+w.timedelta(hours=1))
            self.assertEqual(sender.call_count,2)

    def test_notice_never_executes_or_displays_provider_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            secret = "PROVIDER_PRIVATE_MESSAGE_'$(command)"
            w.save(state/'state.json',{'status':'BLOCKED','reason':'RuntimeError','summary':secret,'next_step':secret})
            sender = unittest.mock.Mock(return_value=True)
            w.publish_attention(state,sender)
            self.assertNotIn(secret,(state/'attention.txt').read_text(encoding='utf-8'))
            self.assertNotIn(secret,str(sender.call_args))

    def test_success_checkpoint_waits_without_spending_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'repo'
            (root/'tools').mkdir(parents=True)
            (root/'tools/SPX_AGENT_TASK.md').write_text('task')
            state = Path(tmp)/'state'
            def fake_git(root,*args):
                return subprocess.CompletedProcess(args,0,stdout=w.BRANCH if args[0]=='branch' else '',stderr='')
            def model_run(executable,root,prompt,output,schema,log):
                w.save(output,{'status':'WAIT_DATA','summary':'No new session','next_step':'Collect complete raw session'})
                return 0
            with patch.object(w,'git',side_effect=fake_git), patch.object(w,'run_codex',side_effect=model_run) as model:
                self.assertEqual(w.tick(root,state,executable='fake'),'WAIT_DATA')
                self.assertEqual(w.tick(root,state,executable='fake'),'waiting')
                self.assertEqual(model.call_count,1)
            self.assertFalse(w.json.loads((state/'state.json').read_text())['push_pending'])

    def test_budget_backoff_and_review_pause(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.assertTrue(w.eligible({}, now, 'a'))
        self.assertFalse(w.eligible({'day':'2026-10-23','calls':2}, now, 'a'))
        self.assertFalse(w.eligible({'next_at':now.timestamp()+1}, now, 'a'))
        for status in ('BLOCKED', 'CANDIDATE_FOR_REVIEW'):
            self.assertFalse(w.eligible({'status':status}, now, 'new'))

    def test_only_new_raw_data_wakes_waiting(self):
        now = datetime.now(timezone.utc)
        for status in ('WAIT_DATA', 'NOT_READY'):
            state = {'status':status,'data_hash':'old'}
            self.assertFalse(w.eligible(state, now, 'old'))
            self.assertTrue(w.eligible(state, now, 'new'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = w.fingerprint(root)
            (root/'RESUME.md').write_text('churn')
            self.assertEqual(before, w.fingerprint(root))
            (root/'artifacts/a').mkdir(parents=True)
            (root/'artifacts/a/raw.json').write_text('{"time":[1]}')
            self.assertNotEqual(before, w.fingerprint(root))

    def test_offline_and_dirty_never_call_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'repo'
            root.mkdir()
            state = Path(tmp)/'state'
            def fake_git(root, *args):
                return subprocess.CompletedProcess(args, 1 if args[0]=='ls-remote' else 0,
                    stdout=w.BRANCH+'\n' if args[0]=='branch' else '', stderr='')
            with patch.object(w,'git',side_effect=fake_git), patch.object(w,'run_codex') as model:
                self.assertEqual(w.tick(root,state,executable='fake'), 'offline_or_git_auth')
                model.assert_not_called()
            def dirty_git(root,*args):
                return subprocess.CompletedProcess(args,0,stdout=w.BRANCH if args[0]=='branch' else (' M file' if args[0]=='status' else ''),stderr='')
            with patch.object(w,'git',side_effect=dirty_git), patch.object(w,'run_codex') as model:
                self.assertEqual(w.tick(root,state,executable='fake'), 'blocked_dirty')
                model.assert_not_called()

    def test_failure_preserves_budget_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'repo'
            (root/'tools').mkdir(parents=True)
            (root/'tools/SPX_AGENT_TASK.md').write_text('task')
            state = Path(tmp)/'state'
            def fake_git(root,*args):
                return subprocess.CompletedProcess(args,0,stdout=w.BRANCH if args[0]=='branch' else '',stderr='')
            with patch.object(w,'git',side_effect=fake_git), patch.object(w,'run_codex',return_value=1) as model:
                self.assertEqual(w.tick(root,state,executable='fake'), 'BLOCKED')
                result = w.json.loads((state/'state.json').read_text())
                self.assertEqual(result['calls'],1)
                self.assertEqual(w.tick(root,state,executable='fake'), 'waiting')
                self.assertEqual(model.call_count,1)

    def test_pending_push_retries_without_model_when_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'repo'
            root.mkdir()
            state = Path(tmp)/'state'
            w.save(state/'state.json',{'status':'WAIT_DATA','data_hash':w.fingerprint(root),'push_pending':True})
            def fake_git(root,*args):
                return subprocess.CompletedProcess(args,0,stdout=w.BRANCH if args[0]=='branch' else '',stderr='')
            with patch.object(w,'git',side_effect=fake_git) as calls, patch.object(w,'run_codex') as model:
                self.assertEqual(w.tick(root,state,executable='fake'),'waiting')
                self.assertTrue(any(call.args[1]=='push' for call in calls.call_args_list))
                model.assert_not_called()
            self.assertFalse(w.json.loads((state/'state.json').read_text())['push_pending'])


if __name__ == '__main__':
    unittest.main()
