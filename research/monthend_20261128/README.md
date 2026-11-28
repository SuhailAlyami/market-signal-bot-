# Month-end SPX (for 2026-11-30), tested 2026-11-28

Hypotheses fixed before running; discovery 1990-2009, test 2010-2026 (Yahoo daily ^GSPC/^VIX); intraday from Dukascopy US500 1m 2025-01..2026-11 (22 month-ends).

- Last trading day (LTD) direction: no stable bias. Up 50% (1990-2009) vs 53% other days; 44% (2010-2026) vs 55%, but all of that
  comes from 2010-2017 (38%); 2018-2026: 50% vs 54% (n.s.). NOT usable.
- LTD explosion day (|C-O| >= 0.75 m): 23% vs 23% (2010-2026). No effect.
- Rebalancing (LTD open->close against month-to-date move): 54% overall, 53% when |MTD| >= 3% (2010-2026, n=87). No edge for the day.
- First trading day of the month up close-to-close: 59/63/59/61% by period vs 53-55% other days. Small, stable (turn-of-month effect).
- Gap direction rule on LTD: 79% vs 80% other days: works as usual.
- Intraday (n=22, descriptive only): month-end last hour moves are larger (mean |15:00->16:00| 19.8 vs 11.7 pts; last 30 min 14.4 vs 9.0),
  direction 50/50. With |MTD| >= 3% the last 30 min went against the month's move 7/8 times: post hoc, tiny sample, NOT claimed.
- Nov 2026 month-to-date at 11-27: -3.7%.
