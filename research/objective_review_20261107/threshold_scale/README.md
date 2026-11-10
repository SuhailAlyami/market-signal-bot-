# Threshold scale R = max(5, 0.67*ATR6) vs control — REJECT_CHANGE_KEEP_CONTROL

Protocol (`protocol.json`, sha256 b520e864...) was committed in ff10de8 before results. Data: 116 CONSUMED sessions (in-sample); 2026-11-05/06 untouched.
Control (k=1.0) reproduces wave_capture exactly (668 signals, 365 legs, 199 matched, 48 early; unit-tested). 4 tests pass.

| Block | arm | signals | early | early excess vs random | matched<=75% | unmatched/session | net pts @cost1, delay 0 |
|---|---|---:|---:|---:|---:|---:|---:|
| older (78) | control | 453 | 32 | +4.3 | 135 | 4.08 | -159.4 |
| older | k=0.67 | 508 | 42 | +10.0 | **134** | 4.80 | -461.5 |
| recent (38) | control | 215 | 16 | +0.9 | 64 | 3.97 | -280.8 |
| recent | k=0.67 | 237 | 23 | +6.7 | 65 | 4.53 | -253.3 |
| all (116) | control | 668 | 48 | +4.8 | 199 | 4.04 | -440.2 |
| all | k=0.67 | 745 | 65 | +17.4 | 199 | 4.71 | -714.8 |

Failed rule: older matched<=75% 134 < 135 (guardrail c). Early gain and positive excess held in both blocks (unlike opening_seed), unmatched/session stayed within +1.0, median lag stayed 15 min.
Net execution points got worse overall (-714.8 vs -440.2). Not rescued: k is not revisited and the rule is not relaxed. Any follow-up needs a new preregistration tested on unused sessions (>=20 collected after 2026-11-04; plan ~55).
Reproduce: `python run_scale.py > summary.json` (needs `../requirements.txt`).
