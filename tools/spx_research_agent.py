"""Bounded local Codex research worker. No broker or trading calls in this runner."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

BRANCH = "research/local-spx-agent"
STATUSES = {"CONTINUE", "WAIT_DATA", "BLOCKED", "NOT_READY", "CANDIDATE_FOR_REVIEW"}


def desktop_notice(title, message):
    """Request a local Windows tray notice; OS settings may suppress display."""
    if os.name != "nt":
        return False
    powershell = shutil.which("powershell.exe")
    if not powershell:
        return False
    # Encode data separately: no model/provider text is interpolated as PS code.
    payload = base64.b64encode(json.dumps({"title": title, "message": message}, ensure_ascii=False).encode()).decode()
    script = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD')) | ConvertFrom-Json
$icon = New-Object System.Windows.Forms.NotifyIcon
try {
    $icon.Icon = [System.Drawing.SystemIcons]::Information
    $icon.Text = 'Suhail SPX Research'
    $icon.Visible = $true
    $icon.ShowBalloonTip(10000, $p.title, $p.message, [System.Windows.Forms.ToolTipIcon]::Info)
    $until = [DateTime]::UtcNow.AddSeconds(12)
    while ([DateTime]::UtcNow -lt $until) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
    }
} finally {
    $icon.Visible = $false
    $icon.Dispose()
}
'''.replace("PAYLOAD", payload)
    encoded = base64.b64encode(script.encode("utf-16le")).decode()
    try:
        result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                 "-EncodedCommand", encoded], capture_output=True, timeout=25)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def publish_attention(state_dir, sender=None, now=None):
    """One notice per unresolved reason, with durable Arabic fallback text."""
    state_path = state_dir / "state.json"
    if not state_path.exists():
        return "no_state"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    status = state.get("status")
    gateway = state.get("needs_gateway") is True
    kinds = {"WAIT_DATA": "data", "BLOCKED": "blocked", "CANDIDATE_FOR_REVIEW": "review"}
    kind = "gateway" if gateway and status in {"WAIT_DATA", "NOT_READY", "BLOCKED"} else kinds.get(status)
    notice_path = state_dir / "attention.json"
    previous = json.loads(notice_path.read_text(encoding="utf-8")) if notice_path.exists() else {}
    if not kind:
        if previous.get("active"):
            previous.update(active=False)
            save(notice_path, previous)
            (state_dir / "attention.txt").write_text("لا يوجد طلب تدخل حالي من عامل سهيل هنتر.\n", encoding="utf-8")
        return "no_attention"
    # Stable reason key. Changing model prose/timestamps must not cause repeated alerts.
    reason = state.get("reason", "") if kind == "blocked" else ""
    key = hashlib.sha256(json.dumps([kind, reason], ensure_ascii=False).encode()).hexdigest()
    now = now or datetime.now(timezone.utc)
    if previous.get("active") and previous.get("key") == key:
        if previous.get("popup_requested") or now.timestamp() < previous.get("retry_at", 0):
            return "deduplicated"
    title = "سهيل هنتر — مطلوب تدخلك"
    messages = {
        "gateway": "أحتاج IB Gateway لجلب بيانات جديدة. افتحه وسجّل الدخول بنفسك، ثم اطلب من Codex متابعة جمع البيانات. لا ترسل كلمة المرور.",
        "data": "الدورة تنتظر بيانات SPX جديدة. افتح Codex واطلب متابعة جمع البيانات. لم يتأكد أن السبب إغلاق IB Gateway.",
        "blocked": "تعذّر إكمال دورة البحث. افتح Codex واطلب فحص state.json والسجل المحلي واستئناف العمل دون حذف التقدم.",
        "review": "اكتملت نتيجة بحث تحتاج المراجعة. افتح Codex لمراجعة الدليل؛ هذا لا يعني ضمان نجاح الكشف أو الربح."
    }
    message = messages[kind]
    requested = (sender or desktop_notice)(title, message)
    notice = {"active": True, "key": key, "kind": kind, "title": title, "message": message,
              "at_riyadh": now.astimezone(timezone(timedelta(hours=3))).isoformat(),
              "popup_requested": bool(requested), "retry_at": now.timestamp() + 3600}
    save(notice_path, notice)
    (state_dir / "attention.txt").write_text(title + "\n" + message + "\n" + notice["at_riyadh"] + "\n", encoding="utf-8")
    return "popup_requested" if requested else "saved_text_only"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=45,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def fingerprint(root):
    """Only market inputs wake WAIT_DATA; code/checkpoint churn must not do so."""
    digest = hashlib.sha256()
    for folder in (root / "artifacts", root / ".hunter-state"):
        if folder.exists():
            for path in sorted(folder.rglob("raw.json")):
                digest.update(str(path.relative_to(root)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def eligible(state, now, data_hash, daily_limit=2):
    if state.get("status") in {"BLOCKED", "CANDIDATE_FOR_REVIEW"}:
        return False
    if state.get("status") in {"WAIT_DATA", "NOT_READY"} and state.get("data_hash") == data_hash:
        return False
    count = state.get("calls", 0) if state.get("day") == now.date().isoformat() else 0
    return count < daily_limit and now.timestamp() >= state.get("next_at", 0)


def run_codex(executable, root, prompt, output, schema, log, seconds=900):
    # Windows npm installs expose codex.cmd; quote only via subprocess.list2cmdline.
    command = [executable, "exec", "--sandbox", "workspace-write",
               "--output-schema", str(schema), "-o", str(output), "-"]
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c",
                   subprocess.list2cmdline(command)]
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE,
                                   stdout=stream, stderr=stream, text=True,
                                   encoding="utf-8", **kwargs)
        try:
            process.communicate(prompt, timeout=seconds)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise RuntimeError("cycle_timeout")
        return process.returncode


def tick(root, state_dir, executable=None):
    state_path = state_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    now = datetime.now(timezone.utc)
    data_hash = fingerprint(root)
    if (state_dir / "STOP").exists():
        return "waiting"
    if state.get("push_pending"):
        if git(root, "branch", "--show-current").stdout.strip() != BRANCH:
            return "wrong_branch"
        if git(root, "push", "-u", "origin", BRANCH).returncode:
            return "push_pending"
        state["push_pending"] = False
        save(state_path, state)
    if not eligible(state, now, data_hash):
        return "waiting"
    executable = executable or shutil.which("codex") or shutil.which("codex.cmd")
    if not executable:
        return "codex_not_installed"
    if git(root, "branch", "--show-current").stdout.strip() != BRANCH:
        return "wrong_branch"
    # Offline ticks consume no model calls and do not spin. Scheduler retries later.
    if git(root, "ls-remote", "--exit-code", "origin", "HEAD").returncode:
        return "offline_or_git_auth"
    if git(root, "status", "--porcelain").stdout.strip():
        state.update(status="BLOCKED", reason="uncommitted_changes_require_recovery")
        save(state_path, state)
        return "blocked_dirty"
    # Save pending local commits before starting any new model work. Never force.
    if git(root, "push", "-u", "origin", BRANCH).returncode:
        return "push_pending"
    day = now.date().isoformat()
    state.update(day=day, calls=(state.get("calls", 0) if state.get("day") == day else 0) + 1,
                 next_at=now.timestamp() + 3600, data_hash=data_hash, status="BLOCKED",
                 reason="cycle_in_progress_or_interrupted")
    save(state_path, state)  # Charge budget BEFORE launching, including crashes.
    run_dir = state_dir / now.strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir()
    output = run_dir / "result.json"
    schema = run_dir / "schema.json"
    save(schema, {"type": "object", "properties": {
        "status": {"type": "string", "enum": sorted(STATUSES)},
        "summary": {"type": "string"}, "next_step": {"type": "string"},
        "needs_gateway": {"type": "boolean"}},
        "required": ["status", "summary", "next_step", "needs_gateway"], "additionalProperties": False})
    prompt = (root / "tools" / "SPX_AGENT_TASK.md").read_text(encoding="utf-8")
    prompt += "\nPrevious runner checkpoint (not evidence of market quality):\n" + json.dumps(state, ensure_ascii=False)
    try:
        code = run_codex(executable, root, prompt, output, schema, run_dir / "private.log")
        if code:
            raise RuntimeError("codex_exit_" + str(code))
        result = json.loads(output.read_text(encoding="utf-8"))
        if result.get("status") not in STATUSES or not all(isinstance(result.get(k), str) for k in ("summary", "next_step")) or ("needs_gateway" in result and not isinstance(result["needs_gateway"], bool)):
            raise RuntimeError("invalid_cycle_report")
        if git(root, "branch", "--show-current").stdout.strip() != BRANCH:
            raise RuntimeError("branch_changed")
        if git(root, "status", "--porcelain").stdout.strip():
            raise RuntimeError("checkpoint_not_committed")
        pushed = git(root, "push", "-u", "origin", BRANCH).returncode == 0
        state.update(result, needs_gateway=result.get("needs_gateway", False), reason="cycle_complete", push_pending=not pushed)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        # No provider messages, auth data or model logs in public checkpoint.
        state.update(status="BLOCKED", needs_gateway=False, reason=type(exc).__name__, next_step="Inspect local private log; recover checkpoint, then use --resume.")
    save(state_path, state)
    return state["status"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--test-notification", action="store_true", help="Test local desktop notice without running Codex or changing budget")
    args = parser.parse_args()
    root, state_dir = args.repo.resolve(), args.state.resolve()
    try:
        with lock(state_dir / "worker.lock"):
            if args.test_notification:
                requested = desktop_notice("سهيل هنتر — اختبار التنبيه", "هذا اختبار فقط. لا يعني أن البوابة مطلوبة الآن.")
                print("popup_requested_not_delivery_confirmed" if requested else "popup_unavailable")
                return
            if args.resume:
                path = state_dir / "state.json"
                state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                state.update(status="CONTINUE", reason="manual_resume")
                save(path, state)  # Does not reset daily budget/backoff.
            print(tick(root, state_dir))
            if not (state_dir / "STOP").exists():
                print(publish_attention(state_dir))
    except (OSError, subprocess.SubprocessError):
        print("busy_or_local_error")


if __name__ == "__main__":
    main()
