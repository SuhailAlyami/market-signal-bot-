# DeMark projected high/low on SPX (daily) — NOT_BETTER_THAN_BASELINES

Source: an educational TikTok clip (samooalgo, "معادلة ديمارك"). Rules and verdict criteria were fixed in the
script docstring before running. Data: Yahoo ^GSPC/^VIX daily (DELAYED_RESEARCH_ONLY), 2010-01-04 .. 2026-11-13, 4243 sessions.

| Mean abs error (points) | DeMark | prior-day H/L | VIX 1-sigma band | close ± ½·20d avg range |
|---|---|---|---|---|
| High 2010-2019 | 8.4 | 9.5 | 12.3 | **8.0** |
| Low 2010-2019 | 10.2 | 11.5 | 14.2 | **9.6** |
| High 2020+ | 27.8 | 30.1 | 39.3 | **27.1** |
| Low 2020+ | 32.6 | 35.2 | 45.5 | **31.2** |

Level strength: when the day's high reaches the DeMark high, it closes back below it 36.5% / 38.0% of the time,
versus 36.7% / 37.2% for the prior-day high; lows 48.8% / 43.6% vs 48.7% / 43.4%. No extra reversal power.

Verdict: DeMark is a reasonable point estimate of the day's high/low, but a plain average-range estimate is
slightly better in both periods, and DeMark levels do not reject price more than yesterday's high/low.
Not added to the live alert. (The VIX band is a containment band, not a point estimate; its larger MAE is expected.)
