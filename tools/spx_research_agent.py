"""Bounded local Codex research worker. No broker or trading calls in this runner."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time

BRANCH = "research/local-spx-agent"
STATUSES = {"CONTINUE", "WAIT_DATA", "BLOCKED", "NOT_READY", "CANDIDATE_FOR_REVIEW"}


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



def commit_checkpoint(root, files):
    """Host-side explicit research checkpoint; model keeps workspace sandbox."""
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode:
        raise RuntimeError("checkpoint_status_failed")
    changed = set()
    for entry in status.stdout.split("\0"):
        if not entry:
            continue
        if any(letter in entry[:2] for letter in "RCD"):
            raise RuntimeError("checkpoint_rename_or_delete_forbidden")
        changed.add(entry[3:])
    if not changed:
        return
    if not isinstance(files, list) or not files or len(files) > 20 or any(not isinstance(x, str) for x in files):
        raise RuntimeError("explicit_checkpoint_manifest_required")
    if len(set(files)) != len(files) or set(files) != changed:
        raise RuntimeError("checkpoint_manifest_mismatch")
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or any(part.startswith(".") for part in path.parts):
            raise RuntimeError("checkpoint_path_forbidden")
        actual = root / name
        if not actual.is_file() or actual.is_symlink() or not actual.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("checkpoint_path_forbidden")
        if name == "RESUME.md":
            continue
        tracked = git(root, "ls-files", "--error-unmatch", "--", name).returncode == 0
        allowed = ((name.startswith("docs/") and path.suffix == ".md") or
                   (name.startswith("artifacts/") and path.suffix in {".json", ".csv", ".md"}) or
                   (path.parent == PurePosixPath(".") and path.name.startswith("research_spx_") and path.suffix == ".py") or
                   (name.startswith("tests/test_spx_") and path.suffix == ".py"))
        if tracked or not allowed or path.name.lower() in {"raw.json", "private.log", "agents.md"} or path.name.lower().endswith(".raw.json"):
            raise RuntimeError("checkpoint_file_not_research")
    if git(root, "add", "--", *files).returncode:
        raise RuntimeError("checkpoint_stage_failed")
    if git(root, "commit", "-m", "Save bounded SPX research cycle checkpoint").returncode:
        raise RuntimeError("checkpoint_commit_failed")


def fingerprint(root):
    """Only market inputs wake WAIT_DATA; code/checkpoint churn must not do so."""
    digest = hashlib.sha256()
    for folder in (root / "artifacts", root / ".hunter-state"):
        if folder.exists():
            for path in sorted(set(folder.rglob("raw.json")) | set(folder.rglob("*.raw.json"))):
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
        "checkpoint_files": {"type": "array", "items": {"type": "string"}, "maxItems": 20}},
        "required": ["status", "summary", "next_step", "checkpoint_files"], "additionalProperties": False})
    prompt = (root / "tools" / "SPX_AGENT_TASK.md").read_text(encoding="utf-8")
    prompt += "\nPrevious runner checkpoint (not evidence of market quality):\n" + json.dumps(state, ensure_ascii=False)
    try:
        code = run_codex(executable, root, prompt, output, schema, run_dir / "private.log")
        if code:
            raise RuntimeError("codex_exit_" + str(code))
        result = json.loads(output.read_text(encoding="utf-8"))
        if result.get("status") not in STATUSES or not all(isinstance(result.get(k), str) for k in ("summary", "next_step")):
            raise RuntimeError("invalid_cycle_report")
        if git(root, "branch", "--show-current").stdout.strip() != BRANCH:
            raise RuntimeError("branch_changed")
        commit_checkpoint(root, result.get("checkpoint_files", []))
        pushed = git(root, "push", "-u", "origin", BRANCH).returncode == 0
        state.update(result, reason="cycle_complete", push_pending=not pushed,
                     checkpoint_commit=git(root, "rev-parse", "HEAD").stdout.strip())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        # No provider messages, auth data or model logs in public checkpoint.
        state.update(status="BLOCKED", reason=type(exc).__name__, next_step="Inspect local private log; recover checkpoint, then use --resume.")
    save(state_path, state)
    return state["status"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root, state_dir = args.repo.resolve(), args.state.resolve()
    try:
        with lock(state_dir / "worker.lock"):
            if args.resume:
                path = state_dir / "state.json"
                state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                state.update(status="CONTINUE", reason="manual_resume")
                save(path, state)  # Does not reset daily budget/backoff.
            print(tick(root, state_dir))
    except (OSError, subprocess.SubprocessError):
        print("busy_or_local_error")


if __name__ == "__main__":
    main()
