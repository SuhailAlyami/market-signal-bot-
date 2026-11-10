"""Reference signal list from the frozen breadth logic on CONSUMED development dates, for a manual
TradingView parity check. Outcome-free: lists decision time, side, R and agreement only. Read-only use of
research/breadth_20261109 (frozen); nothing there is modified."""
import json
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]/'breadth_20261109'
sys.path.insert(0, str(B))
from breadth_core import aggregate5, agreement, detect  # noqa: E402
from inputs import dev_inputs  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

LO, HI = '2026-10-29', '2026-11-04'  # consumed dates; also within TradingView 5m chart history
RIYADH = ZoneInfo('Asia/Riyadh')
sessions, _, closes = dev_inputs()
out = []
for day, raw, _, step, _ in sessions:
    if not LO <= day <= HI:
        continue
    for s in detect(aggregate5(raw, step)):
        bar_open = s['decision'].replace(second=0)  # decision = close of the 5m bar
        out.append({'day': day, 'decision_ny': s['decision'].isoformat(), 'decision_riyadh': s['decision'].astimezone(RIYADH).strftime('%Y-%m-%d %H:%M'),
                    'signal_bar_open_ny': (bar_open - __import__('datetime').timedelta(minutes=5)).strftime('%H:%M'),
                    'side': 'UP' if s['side'] == 1 else 'DOWN', 'R_points': round(s['r'], 2),
                    'agreement_of_10': agreement(closes, s['decision'], s['side'])})
json.dump({'scope': f'frozen wave detector + breadth agreement on consumed dates {LO}..{HI}; outcome-free; ^GSPC Yahoo 5m',
           'signals': out}, sys.stdout, indent=1)
