# SPX-only v1: engineering isolation passes; predictive objective still fails

Rules/protocol were committed as
`e34df76031a58e2b4b1c54af356ce727f3fe6bcc` BEFORE acquiring this diagnostic
sample. No candidate threshold was changed after seeing these results.

Source: IBKR connected-tool contract resolution returned exact US SPX IND,
CBOE, contract416904. A ONE_DAY/ONE_MIN history request returned241 observations
from2026-10-22T13:30Z to17:30Z. Its chart_end was the future requested session
end20:00Z, not receipt time. The replay bounded completion by actual receipt
17:30:25.772Z and excluded the unfinished17:30bar, retaining240bars. The input
contains OHLC only; no fake Volume column was created. Live entitlement and
arrival-time latency were not verified for this historical replay.

The screenshot and this incomplete session are consumed development, not
independent validation. First eligible decision is14:01UTC (10:01NewYork,
17:01Saudi); the thirty-bar warm-up cannot claim to catch earlier opening
movement. A 10-minute observable future horizon censors the last candidate
windows. Native SPX cash gaps are never filled.

Independent movement labels retain the existing horizon10, max(0.06% of price,
2 prior ATR) target and25%onset distance. With no native5secondSPX input, onset
is conservatively the START of the first minute whose high/low touches that
distance. Intraminute order is unknown; this is not a comparison against the
old ES fine-time sample. The existing strict anchor/one-to-one matching rule
was retained. `per session` below means this one PARTIAL session, not a
forecast of a full-day alarm rate.

| Stage | Scored | Matched movements /16 | Early movements /16 | Precision | Unmatched | Median lead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| WATCH |29|8|1|27.59%|21|-1minute|
| Two-close confirmation |17|4|1|23.53%|13|-1minute|

WATCH early precision is1/29 (3.45%), early recall1/16 (6.25%);28warnings failed
the strict early objective, including late matches. Confirmation early
precision1/17 (5.88%). There were31WATCH transitions total;2 lacked a complete
forward evaluation horizon. No original-production baseline is invented:
the old SPX model requires ES observations unavailable in this sample.

This model fails the existing quality objective. More visible markers are
not success. It is NOT_READY and must not replace a live recommendation
strategy or be advertised as having caught the screenshots in real time.
Neither a Telegram delivery nor a Windows Gateway run happened here.

## Real engineering changes, distinct from the failed quality experiment

* SPX price detection no longer calls es_fetch, uses helper volume or requires
  NQ. Native source identity is enforced.
* The independent entry point starts SPX directly without the ES launcher or
  option-chain initialization. The prior production sender path is not used
  for these unvalidated research events.
* An opposite setup clears the old SPX scenario before confirmation and can
  start immediately. Durable per-bar dedupe prevents repeated evaluation.
* NYSE calendar is injected for cash SPX; generic ES behavior retains its
  original calendar dynamically, including mocked outage behavior in tests.
* Event metadata identifies the new rule and pattern; rejection reasons and
  current state are visible. Legacy Pine remains explicitly a comparison,
  not a tested port of the new SPX-only model.

Verification:14SPX-specific offline tests (price logic, future independence,
calendar/DST/earlyclose, opposite lifecycle, completed-bar replay) plus23existing
runtime tests pass. Native SDK/Windows process and full repository CI are
separate checks. See the raw capture and reproducible replay result under
`artifacts/spx_only_development/`. Run:

```
python replay_spx_price_watch.py --input artifacts/spx_only_development/raw.json --output replay.json --protocol-commit e34df76031a58e2b4b1c54af356ce727f3fe6bcc
```

The next research hypothesis must change information or justified forecasting
logic, not loosen these measured acceptance criteria. No untouched holdout,
paid resource, order or subscription was used. Objective incomplete.
