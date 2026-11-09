# Price-only CFD models: Oct27 development and Oct29 partial transfer

Status: NOT_READY; promising descriptive evidence for RANGE_READY, no winner activated, no subscription or external alert.

Protocols committed before results:
- c169db6a4f064dbf2969bd5872cda82f5395edf3: CFD_PRICE_ONLY_PROTOCOL.md.
- 746f24532464283d44c1cf4bf4a6c1ecccd72455: CFD_PRICE_ONLY_TRANSFER_PROTOCOL.md.

Source implementations: tradingview/Suhail_Hunter_PRICE_RESEARCH.pine and tradingview/Suhail_Hunter_PRICE_TRANSFER.pine. Actual TradingView Pine compilation and rendered results observed on CAPITALCOM:SPX500 standard1minute. Only OHLC, no delayed ES/helper or synthetic exchange volume. Fixed parameters unchanged between dates.

Evaluation: next consecutive minute Open as a reference only; target1 priorATR20, adverse boundary0.75ATR, ten-minute maximum, exact consecutive minutes; simultaneous target/stop in one OHLC bar counted ambiguous; missing/invalid bars censored. No fills, costs, fees, spreads, option or CFD P&L.

| Date KSA / model | Decisions | Target first | Stop first | Timeout | Both | Gap/input | Pending | Mean signed timeout points |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Oct27 full / RANGE_READY | 38 | 17 | 18 | 1 | 1 | 1 | 0 | +1 |
| Oct27 full / FAILED_BREAK | 53 | 18 | 34 | 1 | 0 | 0 | 0 | -1 |
| Oct27 full / BODY_BASELINE | 131 | 48 | 79 | 0 | 2 | 2 | 0 | N/A |
| Oct29 decisions00:00–10:45 / RANGE_READY | 16 | 10 | 6 | 0 | 0 | 0 | 0 | N/A |
| Oct29 decisions00:00–10:45 / FAILED_BREAK | 30 | 14 | 16 | 0 | 0 | 0 | 0 | N/A |
| Oct29 decisions00:00–10:45 / BODY_BASELINE | 59 | 22 | 36 | 0 | 0 | 1 | 0 | N/A |

Reference hit fraction only among target-first/stop-first observations (excluding ambiguous/timeouts/gaps, all of which remain in the table): RANGE_READY17/35=48.6% vs baseline48/127=37.8% on Oct27; RANGE_READY10/16=62.5% vs baseline22/58=37.9% on Oct29 partial. These fractions have small/overlapping market samples and different model-selected timestamps. They are not independent statistical evidence of profitability or full-market early-explosion precision/recall. They must not be compared directly with the earlier five-minute directional-sign diagnostic.

Interpretation: RANGE_READY is more promising than the prior final-gate relaxations on these two fixed diagnostics. FAILED_BREAK does not show a similar advantage over a simple body baseline. Do not choose or enable a production winner on these results. No parameters were retuned after viewing either result.

Critical limitations:
- Oct27 is a retrospective transfer/development date, not chronological forward validation.
- Oct29 chart had already been visible during debugging, and prior rule diagnostics used this feed; its partial result is NOT a pristine blind holdout.
- Oct29 covers Asia/London only, not NY RTH. Captured coverage extended Oct19 01:00 to Oct29 11:03 KSA; decision cutoff was fixed at10:45 so future bars were used only for outcomes.
- No retained raw export, independent prefix/future-poison audit or per-event reproduction yet.
- No early-explosion event labels, recall/lead-time metrics, latency measurement, live execution or confidence calibration.
- Hypothetical boundaries in broker CFD prices cannot be substituted for cashSPX/option premiums.
- Pine historical marks rebuild on reload. No claim of durable unattended collection or working server alerts under Basic.
- Older chart annotations visible from another script are not measurements from these three models.

Next: freeze RANGE_READY as a candidate, preserving all comparators, and collect a genuinely prospective untouched time interval before evaluating it. Validate price-data replay and causality, add per-event outcome evidence, then assess early-event labels/false alarms and NY behavior. No paid plan is justified solely by this report.
