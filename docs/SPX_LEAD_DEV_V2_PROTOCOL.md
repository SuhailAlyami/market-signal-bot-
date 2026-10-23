# SPX lead hypotheses v2 — consumed-data development only

Motivation: the v1 price candidate first appeared at/after conservative onset
in11of16consumed events. Define three alternatives before running their outcomes.
This document is frozen separately before execution; the Oct22 sample is already
consumed, so this does NOT create an independent test or permit deployment.
Do not change v1 rules, selection, matching, thresholds or acceptance gates.

Inputs: native SPX IND OHLC, completed1m bars; same raw file/cutoff/independent
event universe as v1. No volume or ES/NQ. Features restart each session; reuse
the v1 validation requiring31contiguous positive valid minutes and prior20ATR.
OLS slopeN is the linear-regression slope of the most recentN completed closes,
including current close, in points/minute; N is fixed at3/5/10. EMA15 and current
body/close-position retain v1 semantics. Prior20levels exclude current bar.

Fixed hypotheses, no search grid or changes after this run:

1. `slope_projection`: UP when3*slope5 >=0.5*priorATR, close>EMA15,
   body>0 and close-position>=0.60. DOWN symmetrically with projection<=
   -0.5*ATR, close<EMA15, body<0 and position<=0.40.
2. `acceleration_projection`: UP when slope3>0,
   slope3-slope10>=priorATR/6, 3*slope3>=priorATR and body>0.
   DOWN uses slope3<0, slope3-slope10<=-ATR/6, 3*slope3<=-ATR, body<0.
3. `prelevel_pressure`: UP when 0<prior20high-close<=0.5*ATR,
   slope5>0, body>0, position>=0.65. DOWN when
   0<close-prior20low<=0.5*ATR, slope5<0, body<0, position<=0.35.
   The current close must still be inside the prior20level; no completed break
   is required. A projected move is a feature, not a claimed target or fill.

All three use the same causal ten-minute model cooldown, before horizon
censoring; the label outcome cannot determine scheduling. No lifecycle or
confirmation waits are added. Compare with ALL existing v1 configurations and
the no-signal baseline on the same data, retaining strict anchor-to-target
one-to-one scoring, conservative wick-minute onset and0/1/2minute simulated
delivery delay. Report pre-anchor auxiliary results separately, never as a
replacement acceptance criterion. Preserve counts, misses, signals, Wilson
intervals, and prefix/future-poison checks; do not report option profitability.

No winner selection, training/validation/holdout claims or acceptance on this
consumed partial session, regardless of apparent improvement. A worse result
must be retained. Stop this fixed experiment after the one specified execution;
do not vary thresholds until a passing number appears. Status remains NOT_READY.
