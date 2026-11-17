# "Hero" 15:15 New York candle breakout on SPX — FAILURE (no edge)

Source: TikTok slides "استراتيجية الهيرو SPX". Rules were fixed in `hero_test.py` before running.
- Reference candle: 15:15 New York (23:15 Riyadh in winter).
- Entry: a 1-minute close beyond its high (CALL) or low (PUT).
- Stop: the candle's midpoint.
- Targets: level 2 / level -1, i.e. 1R beyond the broken level; also 2R.
- Exit: at the close otherwise.

Data: Dukascopy US500 1-minute bid bars, 479 sessions from 2025-01-02 to 2026-11-10 (stored on branch cursor/early-explosion-lead-e4c9). DELAYED_RESEARCH_ONLY. Underlying points only; option prices are not modelled.

| Variant | Trades | Win % | Mean pts/trade | Profit factor | 2025 mean | 2026 mean |
|---|---|---|---|---|---|---|
| 5-min candle, target level 2 | 462 | 44.8 | −0.20 | 0.90 | −0.74 | +0.42 |
| 5-min candle, target level 3 | 462 | 28.8 | −0.27 | 0.90 | −1.24 | +0.85 |
| 15-min candle, target level 2 | 446 | 39.9 | −0.59 | 0.82 | −0.92 | −0.21 |
| 15-min candle, target level 3 | 446 | 32.5 | −0.50 | 0.86 | −0.67 | −0.31 |

Every variant loses over the full sample, before spread and option costs. The 2026 gain on the 5-minute version reverses the 2025 loss, so it is unstable. The mirrored trade (fading the breakout) averages +0.07 to +0.60 points, which is too small to cover costs. Not added to any alert.
