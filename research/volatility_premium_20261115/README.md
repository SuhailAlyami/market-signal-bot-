# Do SPX option buyers overpay? Implied (VIX) vs subsequent realized volatility, 1990-2026

Descriptive measurement, not a trading rule. Data: Yahoo daily closes ^GSPC and ^VIX, 1990-01-02..2026-11-13 (9,286 common days), fetched 2026-11-15, DELAYED_RESEARCH_ONLY. Realized = annualized close-to-close volatility over the next 21 trading days. Premium = VIX - realized (vol points).

| Period | Days | VIX > realized | Mean premium | Median | Worst |
|---|---:|---:|---:|---:|---:|
| 1990-2026 | 9,264 | 86% | +4.10 | +4.72 | -72.0 |
| 1990-1999 | 2,527 | 92% | +5.45 | +5.51 | -16.0 |
| 2000-2009 | 2,515 | 82% | +3.35 | +4.00 | -49.9 |
| 2010-2019 | 2,516 | 84% | +3.68 | +4.53 | -28.3 |
| 2020-2022 | 756 | 79% | +3.64 | +5.39 | -72.0 |
| 2023-2026 | 950 | 89% | +3.96 | +4.58 | -31.1 |

Reading: 30-day SPX options were priced above the volatility that followed on 86% of days, in every decade, including after 2023. Buyers of options pay this premium on average; sellers collect it but carry rare, very large losses (worst -72 vol points in 2020). This is volatility (not direction) and 30-day (not 0DTE); it is not a P&L, ignores spreads/fees, and proves no strategy. Consistent with the published variance risk premium literature (e.g. Carr & Wu 2009).
