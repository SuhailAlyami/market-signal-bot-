"""Build the text context fed to the Gemini CLI agents (stdlib only, no network).

  python agents/build_context.py review <diff_file> <pr_meta_file> <out_file>
  python agents/build_context.py audit  <runs_file> <out_file> [--focus N]

The context is capped so it fits the free AI Studio quota. Each agent only reads text and writes a
report. It never sees the GitHub token, never pushes code and never sends Telegram messages.
"""
import datetime as dt
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_CHARS = 180_000          # ~45k tokens, well inside the Gemini flash free-tier limits
MAX_FILE_CHARS = 40_000

# Weekly rotation over the known defects listed in AGENTS.md.
FOCI = [
    ('بيانات السوق: الحداثة والتوقيت والصيفي/الشتوي والشموع غير المكتملة',
     ['spx_cash_session.py', 'session_health.py', 'early_globex_watch.py', 'ibkr_market_data.py',
      'range_alert/daily_range.py', 'gamma_radar/intraday.py']),
    ('التنبيهات: الحالات وإزالة التكرار وعدم الإرسال المزدوج والفشل المغلق',
     ['telegram_signal_delivery.py', 'github_signal_delivery.py', 'globex_render_worker.py',
      'hunter_runtime.py', '.github/workflows/range_alert.yml']),
    ('البحث: تسرب المستقبل وتقسيم walk-forward وخط الأساس',
     ['range_alert/explosion_research.py', 'range_alert/evaluate_range.py', 'backtest_explosion.py',
      'frozen_day_research.py']),
    ('سير العمل في GitHub Actions: الموثوقية واستهلاك الدقائق والأسرار',
     sorted(str(p.relative_to(ROOT)) for p in (ROOT / '.github/workflows').glob('*.yml'))),
    ('الاختبارات: فجوات التغطية للمسارات الحرجة',
     ['spx_primary.py', 'gamma_radar/radar.py', 'range_alert/explosion.py', 'strategy_rules.py']),
]


def read(path, limit=MAX_FILE_CHARS):
    p = ROOT / path
    if not p.is_file():
        return f'[missing: {path}]'
    text = p.read_text(encoding='utf-8', errors='replace')
    return text if len(text) <= limit else text[:limit] + f'\n[... truncated {len(text) - limit} chars]'


def section(title, body):
    return f'\n===== {title} =====\n{body.rstrip()}\n'


def cap(text):
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + '\n[... context truncated]'


def git_log(n=25):
    try:
        return subprocess.run(['git', 'log', '--oneline', f'-{n}'], cwd=ROOT, capture_output=True,
                              text=True, timeout=20).stdout
    except Exception as exc:  # shallow clone or no git: context is still useful without it
        return f'[git log unavailable: {exc}]'


def focus_index(today=None, override=None):
    if override is not None:
        return override % len(FOCI)
    today = today or dt.date.today()
    return today.isocalendar()[1] % len(FOCI)


def build_review(diff_text, meta_text):
    parts = [section('AGENTS.md (project rules)', read('AGENTS.md', 8_000)),
             section('PR metadata', meta_text),
             section('PR diff', diff_text)]
    return cap(''.join(parts))


def build_audit(runs_text, idx):
    title, files = FOCI[idx]
    parts = [section('AGENTS.md (project rules)', read('AGENTS.md', 8_000)),
             section('FOCUS OF THIS WEEK', title),
             section('Recent commits', git_log()),
             section('Recent workflow runs (name, conclusion, event, time)', runs_text[:6_000])]
    budget = MAX_CHARS - sum(map(len, parts))
    for f in files:
        chunk = section(f'FILE {f}', read(f))
        if len(chunk) > budget:
            parts.append(section(f'FILE {f}', '[skipped: context budget reached]'))
            continue
        parts.append(chunk)
        budget -= len(chunk)
    return cap(''.join(parts)), title


def main(argv):
    mode = argv[1]
    if mode == 'review':
        diff = pathlib.Path(argv[2]).read_text(encoding='utf-8', errors='replace')
        meta = pathlib.Path(argv[3]).read_text(encoding='utf-8', errors='replace')
        pathlib.Path(argv[4]).write_text(build_review(diff, meta), encoding='utf-8')
    elif mode == 'audit':
        runs = pathlib.Path(argv[2]).read_text(encoding='utf-8', errors='replace')
        override = int(argv[argv.index('--focus') + 1]) if '--focus' in argv else None
        text, title = build_audit(runs, focus_index(override=override))
        pathlib.Path(argv[3]).write_text(text, encoding='utf-8')
        print(title)
    else:
        raise SystemExit(f'unknown mode {mode}')


if __name__ == '__main__':
    main(sys.argv)
