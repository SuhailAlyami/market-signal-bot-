# Breakout detector: is the volume filter real, and is 2.0x better than 1.5x? — 2026-11-27

Rule = the live detector (`render_breakout.py`, `worker/src/index.js`): SPY 5m, 6-bar box, stop entry 1 tick beyond on
the first break within 6 bars, stop = other side, target 1.5 R, exit after 12 bars. Slippage 1 tick each way only:
**R here is on the underlying, not SPX option P&L.** Reproduce: `./fetch_data.sh && python vol_test.py` → `result.txt`.

## 1. The volume filter holds on instruments it was never tuned on
Same live rule on 10 large stocks (AAPL AMZN AVGO BRK-B GOOGL JPM META MSFT NVDA TSLA), 5m:

| Set | with volume ≥1.5× | without volume |
|---|---|---|
| Same dates as the SPY selection (≤ 11-13) | **+0.038 R** (n=933) | −0.046 R (n=2495) |
| New sessions after 11-13 (no prior research saw them) | **+0.168 R** (n=107) | −0.012 R (n=320) |

The gap between the two columns has the same sign everywhere (SPY train, SPY test, stocks, new sessions).
The absolute edge is small: the session-clustered CI of the volume rule includes 0 in both stock sets.

## 2. Two variants fixed in advance; choice on SPY train only
| Variant | SPY train | SPY test | Stocks ≤ 11-13 | Stocks new |
|---|---|---|---|---|
| live 1.5× | +0.066 (69) | +0.100 (39) | +0.038 (933) | +0.168 (107) |
| **H1 volume ≥ 2.0×** | **+0.124 (42)** | **+0.233 (22)** | **+0.080 (465)** | **+0.226 (49)** |
| H2 break with the session direction | +0.017 (48) | +0.054 (23) | +0.008 (657) | +0.321 (79) |

H1 has the best train result and beats the live rule on all three held-out sets → adopted (2.0×).
H2 lost on train → rejected, even though its last cell looks best (that cell was not allowed to choose).
Not a knife-edge (diagnostic, not used to choose): on the stocks 1.75×–2.5× all give +0.08 to +0.09 R vs +0.05 at 1.5×.

## Limits
- Still not proven: SPY test n=22, CI −0.15..+0.61. Cost: about 40% fewer signals (SPY 64 vs 108 in 60 sessions, ~1 a day).
- The stocks share the same market days as SPY (cross-instrument check, not a long time holdout). Yahoo 5m, possibly delayed.
- Live code after the change matches this research on SPY 63/64 trades (the one difference is the dataset's first day, as before).
