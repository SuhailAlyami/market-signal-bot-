# PDF rules and safe integration — 2026-10-22

Owner supplied `V profile 2_merged_compressed (1).pdf`, 332 pages,
16,351,388 bytes. SHA256:
`6bb546eece13f41fc907ad2b5995b6758f379cfcfccf9f2096a91892dd51978d`.
Page numbers below are PDF pages, not the different printed book numbers.
The original PDF stays outside Git. Extraction/rendering tools are local tools,
not new application requirements. Text extraction is imperfect for Arabic fonts;
pages 40–119 have no extractable text. Rendered representative pages were reviewed,
including the CRT distinction between a closed breakout and a wick/reclaim.
This is a targeted rule review, not a claim that every illustrated page was transcribed.

## Rules mapped to actual inputs

| Pages | Rule in supplied material | Implementation / limitation |
| --- | --- | --- |
| 1–6 | Accumulation, false break, reclaim; stop beyond manipulation extreme; 2R | Observe native prior-20-bar range, strict wick breach **and completed close back inside**; record extreme/opposite boundary as references, not executable orders. Twenty bars is our explicit engineering choice, not a prescribed book parameter. |
| 7–14, especially 11 | Liquidity sweep is confluence, not a standalone entry | Never turn a sweep observation into a recommendation or replace existing confirmation gates. Both range edges swept in one candle is AMBIGUOUS. |
| 20–25, 145–156 | FVG inversion needs a candle close; several separate confirmations | Detect three-candle wick gaps and first subsequent close through the entire opposite gap. Past close-through consumes it. FVG alone is not a completed TTC setup. |
| 22, 28–30, 124–132 | Example five-point gap, ES/NQ context | Do not transplant an instrument-specific five-point example to SPX/ES blindly. NQ SMT is unverified; do not claim it from ES/SPX agreement. |
| 40, 50, 60, 70, 80 (rendered) | CRT range; real break versus false break; HTF/LTF separation | Record reclaim separately from the live continuation detector. No relabeling the continuation strategy as CRT/TTC. Higher-timeframe delivery is not certified. |
| 145–156 | HTF FVG rejection, iFVG, CISD, clear opposing liquidity; SMT optional refinements | Output `complete_pdf_setup=false`, explicit unverified HTF/CISD/SMT; no A+/win-rate label. A recent rolling extreme is an observable reference, not proven resting liquidity. |
| 197–203 | Price-level volume, tick granularity, POC; don't trade POC blindly | Current OHLCV and quote callbacks cannot reconstruct true traded volume-at-price. `volume_profile_status=unavailable_trade_volume_at_price`. No distributing bar volume into invented price bins/POC/VAH/VAL. |
| 210–223 | Accumulation/trend/rejection volume clusters and return to those levels | Require actual bounded trade-price/size history and a defined complete anchor before implementing these setups. SPX index has no native traded volume; ES volume/levels must remain labeled ES. |
| 228, 260–264 | Volatility-adapted risk, targets before opposing volume, stops behind structure | Keep existing ATR risk gate and 1R/2R targets; don't invent missing volume clusters or copy forex pip settings to ES/SPX. |

Some chapters suggest entry on first touch, while others require multiple confirmations.
They are different models, not a single universal checklist. Existing two-close,
relative-volume, directional, data-age, option-quote and dedupe gates stay unchanged.
The PDF's quoted win rates and institutional narratives are not validated results.

## What runs

`price_action_context.observe` adds a bounded, causal **SHADOW** annotation to each
new completed-bar observation in `hunter_runtime.py`. It uses only 22 bars ending
at the selected index, requires timezone-aware contiguous minutes and valid native
OHLC, and never changes lifecycle events, entry/stop/targets, publication or orders.
Body/range divided by prior-20 ATR are measurements; no invented momentum threshold.
Context exceptions are recorded and isolated from the existing detector.
Health reports only version/status/bar time, not price references or option quotes.

The Pine v6 port exposes optional gray SHADOW sweep marks (off by default) and
FVG/iFVG directions in the data window. All calculations are on confirmed candles;
no additional alerts. Python/Pine source fingerprint now includes the context module.
Pine's existing 31-bar data gate is stricter than the standalone 22-bar context helper.
Actual TradingView compilation remains unverified; source checks are not compilation.

## Verification and promotion

Focused tests cover reclaim versus mere touch, ambiguous two-sided sweeps,
first-close-only inversion, future-bar independence, no input mutation, gaps,
invalid OHLC, missing native index volume, and identical lifecycle events/state
even when context raises. Existing affected runtime/relay/Pine tests are retained.
No Telegram verification message is sent.

This improves observable classification, **not proven predictive accuracy**. Promotion
to notification gates requires chronological training/validation/untouched holdout,
event precision/recall, false alarms, misses, lead time and cost/latency limitations,
compared with the frozen baseline. Existing NOT_READY/negative evidence is preserved.
True volume-profile models additionally need actual ES trade-price/size coverage;
no subscription, tick entitlement or extra paid service is enabled by this change.
