# Early WATCH investigation: development only, NOT_READY

The warning objective is advance notice before movement onset. A confirmed
entry after two breakout closes is not counted or described as early merely
because it has a WATCH ancestor. Each stage has its own timestamp and score.

## Fixed hypotheses and comparable baseline

1. Commit138d4f70a5231b3f22dfbb213df4577dc266ca74 fixed pre-breach volume
   pressure at the compressed5minute edge, with separate WATCH and entry state.
2. That development run showed excessive range-identity warning churn and
   mostly reactive timing. Commitb21ddc3f40159dee27e614fb04129917bbebaa04 then
   froze one warning at compression-episode FORMATION, before relative-volume
   pressure. It does not rearm until a completed context leaves compression.

Both use exactly the previously consumed ten September ESU6 sessions and the
same223 movement events/five-second conservative onsets. No July holdout or
new paid data was used. These are explicit separate hypotheses, not a parameter
grid or independent validation. Warning geometry can differ from entry rules;
it never bypasses common entry risk, freshness or notification gates.

| Stage/model | Scored | Matched movements | Early movements | Precision | Early recall | False/session | Median lead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original SETUP | 49 | 15 | 4 | 30.61% | 1.79% | 3.4 | -3.00m |
| SETUP with rejected plans released | 53 | 16 | 4 | 30.19% | 1.79% | 3.7 | -2.50m |
| Pre-breach pressure WATCH | 596 | 123 | 17 | 20.64% | 7.62% | 47.3 | -1.667m |
| Pressure separate entry | 97 | 33 | 3 | 34.02% | 1.35% | 6.4 | -2.833m |
| Compression-episode WATCH | 196 | 41 | 14 | 20.92% | 6.28% | 15.5 | -0.667m |
| Episode separate entry | 4 | 1 | 0 | 25.00% | 0% | 0.3 | -2.25m |

Global movement precision includes later matches; only strictly positive
onset-minus-decision lead counts as early. Median is over ALL matched movements,
not only a selected early subset. Paired95% early-F1 difference versus the
appropriate SETUP baseline includes zero for both candidates. Neither candidate
qualifies for spending the untouched independent sample or live adoption.

## Timing diagnostic, not a rewritten acceptance metric

The existing strict scorer requires event anchor_index<=warning index. That
penalizes legitimate forecasts made before a later event's anchor. We audited
this independently of detector inputs: remove ONLY that anchor lower bound,
retain the SAME labels, direction, earliest one-to-one event assignment,
target-minute deadline and ten-index horizon for every compared model.
This is explicitly a development sensitivity audit, not a promotion criterion.

Under that audit, episode WATCH captures36early/223 (16.14%),precision31.12%,
13.5false/session,medianlead+0.417m; the repaired baseline captures9early/223,
precision39.62%,3.2false/session,medianlead-1.417m. Pressure WATCH captures40early
but still46.3false/session. Thus an unfair anchor restriction explains some
under-crediting, but removing it does NOT rescue these models. No matching
definition was selected to claim success or applied to a fresh test after
looking at its outcomes. The primary unchanged scores remain above.

## Concrete lifecycle defect repaired separately

The runtime marks TRIGGER before complete_plan runs. Rejection previously left
that nonexistent entry active until expiry and then cooldown. New reject_plan
releases ONLY the matching event identity, persists READY, leaves last-bar and
notification dedupe intact, and adds no position cooldown. A late rejection
cannot remove a newer scenario. Failure to persist fails closed.

The ES relay/local path and SPX strategy/option rejection path call this method.
Accepted plans retain their current lifecycle. Existing Pine underlying-state
logic releases ineligible plans, with its source fingerprint updated. This is
maintenance of the existing script, not a validated early-warning Pine release;
actual TradingView compilation and exact broker option data parity are not
claimed. The repair creates4more baseline setups here but zero additional
early matches: it corrects state semantics, not proven predictive quality.

Isolated production fix PR40 contains NONE of these new warning models.
42 affected tests passed, final SPX/fingerprint adjustment passed8SPXtests;
four pressure and three episode correctness tests passed. All five checks for
PR40 head061b0bfaf234902f5a404e348e9c59d27e844163 passed, including Windows and
Ubuntu. It merged as0564c0667be0373a65831c2d514bf51a378ed9bf. Deployment and
post-change feed evidence are operational checks only, never quality proof.

## What remains possible and what is not established

There is no new access, subscription or infrastructure blocker. Available OHLCV
supports these reproducible tests and the definite lifecycle fix. It has NOT
yet supplied an acceptable directional pre-acceleration predictor. More warnings
and higher event coverage cannot be sold as an edge when false alarms/lead fail.
Do not declare the original model accepted because alternatives failed.

The untouched twenty-session sample is still reserved for a justified candidate
that clears development gates. A complete true trade-volume profile from the
reference remains a distinct untested input hypothesis; seconds-long tick probes
are insufficient and candle volume must not be spread into invented price bins.
There is no guarantee that collecting it will yield a predictor. No large tick
backfill, paid service, trade or Telegram test was launched. New warning models
remain disconnected from live senders. The broader improvement objective is
still incomplete, with full matching new Pine conditional on real independent
acceptance, not on CI or maintenance deployment.
