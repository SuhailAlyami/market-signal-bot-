# Do the ICT/SMC filters catch moves? — 2026-11-24 — verdict: NO (no filter beats random bars)
Success = +2 ATR20 in the signal direction before −1 ATR20 against, within the horizon (owner's definition). A bar
that touches both counts as a loss. Baseline = the same rule on every bar, both directions.

| Data | Horizon | Baseline | sweep | FVG | sweep+FVG | pre-level (rvol) |
|---|---|---|---|---|---|---|
| SPY 5m, 60 sessions | 30 min | 14.6% | 13.8% | 15.9% | 16.9% (n=71) | 17.6% (−0.09 R) |
| SPY 5m | 60 min | 23.4% | 23.3% | 24.3% | 23.9% | 22.7% |
| SPX 5m, 60 sessions | 30 min | 16.1% | 15.8% | 17.2% | 14.3% | 24.8% (+0.05 R)* |
| **SPX 1m, 10 untouched sessions** | 5 min | 19.1% | 17.2% | 19.1% | 16.3% | n/a (no volume) |
| SPX 1m, untouched | 15 min | 32.1% | 30.2% | 31.0% | 34.9% (n=129) | n/a |

\* The single cell above its baseline does not reproduce on tradable SPY (17.6%, −0.09 R), and it is 1 of about 20 comparisons.
Average R is about 0 everywhere: the filters do not separate good entries from random ones.
Not tested: the owner's TradingView "All Sessions v2.2.1" (its code is not in the repo). `tradingview/*.pine` port the pre-level rule tested here.

# Compression → breakout with an OCO bracket — volume surge is the only filter with the same sign in train and test
SPY 5m, train sessions 1–40 (2026-08-21..10-16), test 41–60 (10-19..11-13). Box = 6 bars; stop = other side of the box; target = 1.5 R.
- Compression (small box vs ATR) did **not** help: q=0.15/0.30 were worse than no filter on train.
- Selected on train: no compression cut, breakout bar volume ≥ 1.5× its 20-bar average. Train +0.066 R (n=69); **test +0.100 R, 54% wins (n=39, CI −0.17..+0.37)**.
- Same bracket without the volume surge: train −0.094 R, test −0.065 R. The difference holds in both halves; pooled with volume +0.078 R (n=108, CI −0.09..+0.25).
- Not proven: the sample is limited by Yahoo's 60-day 5m history. Deployed as a labelled live detector in `worker/` and scored every evening from 2026-11-16 (JS port matches the Python trades 107/108; the one difference is the dataset's first day).
