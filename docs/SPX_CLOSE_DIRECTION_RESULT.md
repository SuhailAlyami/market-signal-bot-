# Close-only v1 result: NOT_READY

Protocol/code were stored in GitHub commit c4b609c429ca337637581935581ac95891eb2ce9
before the outcome run. Data: retained native IBKR daily exports; close arrays
agree across two request windows from the SAME provider. This is not independent
verification. No new provider request, edited price or deleted session.

Window contains 295 consecutive sessions, 2024-10-28..2025-12-31. Validation:
2025-04-01..2025-06-30, 62 predictions. Label is next-close change beyond +/-0.1%;
this is NOT the issued model's +/-0.1 ATR label. No highs/lows/ATR/volume used.

| Fixed model | Correct / total | Accuracy | Balanced accuracy |
|---|---:|---:|---:|
| Ridge close-only v1 | 33 / 62 | 53.23% | 37.00% |
| Expanding majority | 34 / 62 | 54.84% | 33.33% |
| Previous-session direction | 24 / 62 | 38.71% | 28.17% |
| Five-session momentum | 29 / 62 | 46.77% | 34.62% |

Actual classes: 34 Bullish, 19 Bearish, 9 Sideways. Candidate recalled 27/34
Bullish, 6/19 Bearish and 0/9 Sideways. It predicted 49 Bullish, 13 Bearish and
zero Sideways. The aggregate 53.23% is not balanced three-class competence and
is not a probability for today's forecast. The difference from majority is
-1.61 percentage points, with paired-bootstrap lower 95% gain bound -12.90pp.
This does NOT establish the candidate is statistically worse; it fails the
predeclared superiority gate. Its apparent gains over the other baselines also
have nonpositive lower confidence bounds. Every comparison failed.

Outcome: NOT_READY. The 2025-07-01..2025-12-31 holdout was NOT evaluated by the
model/evaluator. Validation is now consumed for this hypothesis: do not retune
on these 62 outcomes then claim independent improvement. Preserve full confusion
matrices, hashes, every forecast and mistake in
artifacts/spx_close_direction_20261026/result.json. No model promotion, confidence
publication, current-day claim, high/low forecast, production alert or trade.

Original OHLC experiment remains WAIT_VALID_DATA. Do not backfill this result
into the issued forecast DB or present it as prospective performance. Next work
requires a separately fixed hypothesis and genuinely independent validation,
not another search over these dates. Native Gateway installation/execution
remains unavailable from this environment.

## Closing-value semantics check
Primary-source review did not establish that the five conflicting OHLC rows may
be safely accepted or repaired. S&P distinguishes constituent official closes
from intraday consolidated prices; that general distinction is not verification
of these five provider candles. The special opening quotation (SOQ) is distinct
from ordinary daily index OHLC and is not a reason to reinterpret these closes
as option settlement prices. No daily ingestion rule was relaxed.

References reviewed:
- https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-equity-indices-policies-practices.pdf
- https://www.spglobal.com/spdji/en/documents/methodologies/methodology-index-math.pdf
- https://cdn.cboe.com/resources/spx/Settlement_of_Standard_AM_Settled_SP_500_Index_Options.pdf
