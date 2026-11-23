"""Send an agent report to Telegram, the project's single notification channel.

  python agents/notify_telegram.py <header> <report_file>

Uses range_alert.daily_range.send, so it shares the same retries and the same TELEGRAM_NOTIFY on/off switch.
Telegram caps a message at 4096 characters, so long reports are split on line breaks.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'range_alert'))
from daily_range import send  # noqa: E402

LIMIT = 3900


def chunks(text, limit=LIMIT):
    out, cur = [], ''
    for line in text.splitlines(keepends=True):
        while len(line) > limit:            # a single very long line
            if cur:
                out.append(cur); cur = ''
            out.append(line[:limit]); line = line[limit:]
        if len(cur) + len(line) > limit:
            out.append(cur); cur = ''
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def main(argv):
    header, body = argv[1], pathlib.Path(argv[2]).read_text(encoding='utf-8').strip()
    parts = chunks(body)
    ok = True
    for i, part in enumerate(parts, 1):
        tag = f'{header} ({i}/{len(parts)})' if len(parts) > 1 else header
        ok = send(f'{tag}\n\n{part}') and ok
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
