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
