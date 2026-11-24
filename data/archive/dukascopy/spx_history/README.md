# SPX / ETF 1-minute history (free, keyless)

Laid out like `data/archive/<SYMBOL>/<YYYY-MM-DD>.csv.gz` in
`SuhailAlyami/market-signal-bot-` (`archive_1m.py` columns exactly):

`timestamp,Open,High,Low,Close,Volume,received_at,timing`

- `timestamp` and `received_at` are UTC ISO (`YYYY-MM-DDTHH:MM:SS+00:00`).
- Session date in the filename is the America/New_York calendar date.
- Main files are regular trading hours only: 09:30–15:59 ET.

Generated 2026-11-11 (Asia/Riyadh). Last complete US session in the files: 2026-11-10.

## What to use for the explosion detector

| Folder | Symbol | Source | Sessions | Range | Volume | Use |
|---|---|---|---:|---|---|---|
| `SPY/` | SPY | Dukascopy bid CFD (`spyususd`) | 466 | 2025-01-02 to 2026-11-10 | broker/CFD volume, **not** exchange volume | **Primary 1m price series (~22 months)** |
| `QQQ/` | QQQ | Dukascopy bid CFD (`qqqususd`) | 466 | 2025-01-02 to 2026-11-10 | same volume caveat | Same |
| `GSPC/` | S&P 500 | Dukascopy US 500 Index CFD (`usa500idxusd`) | 479 | 2025-01-02 to 2026-11-10 | CFD volume | Cash-index proxy (small futures-style basis vs official `^GSPC`) |
| `VIX/` | vol index | Dukascopy Volatility Index CFD (`volidxusd`) | 477 | 2025-01-02 to 2026-11-10 | sparse | **Weak proxy only** — often several percent away from official CBOE `^VIX`, many missing minutes |
| `VIX1D/` | `^VIX1D` | Yahoo Finance 1m | 17 | 2026-10-19 to 2026-11-10 | Yahoo | Official short history; no long keyless 1m source found |
| `yahoo/<SYM>/` | SPY, QQQ, GSPC, VIX, VIX1D | Yahoo 1m RTH | 17 | 2026-10-19 to 2026-11-10 | official ETF volume | Cross-check and official volume / official VIX |
| `yahoo_5m/<SYM>/` | same | Yahoo 5m RTH | 28 | 2026-10-02 to 2026-11-10 | official | Yahoo's longer 5-minute window (~40 calendar days) |

Do **not** mix Dukascopy Volume with Yahoo Volume when computing RVOL. Price-based signals (momentum %, ATR) on SPY/QQQ are appropriate.

## Sources (all keyless, no account)

1. **Dukascopy Bank public historical feed** via `dukascopy-node`
   - https://www.dukascopy-node.app/instrument/spyususd
   - https://www.npmjs.com/package/dukascopy-node
   - Underlying feed: `https://datafeed.dukascopy.com/datafeed/`
   - Price type: bid, interval: 1 minute, requested 2025-01-01 through 2026-11-11 UTC.
2. **Yahoo Finance chart API** (no key)
   - `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m|5m&includePrePost=true`
   - 1m: older than ~23 calendar days returned HTTP 422. Observed 1m span: 2026-10-19 to 2026-11-10 (17 RTH sessions).
   - 5m: observed 2026-10-02 to 2026-11-10 (28 RTH sessions).

## Quality (SPY, the priority series)

- 466 RTH sessions, 181,041 minute bars, **zero OHLC violations**.
- 18 missing weekdays in the span are US market holidays (including 2025-01-09, National Day of Mourning for Jimmy Carter). No unexpected full-session holes.
- 427 sessions have every 09:30–15:59 bar (or the 210-bar early-close grid). 32 sessions miss 1–5 minutes. 7 sessions miss more than 5 minutes:
  - 2025-01-07: 10 min (open 09:30–09:35 and 09:38–09:41)
  - 2025-03-25: 17 min (13:51–14:07)
  - 2025-09-26: 6 min (10:51–10:56)
  - **2026-03-04: 44 min (09:30–10:13)** — largest SPY gap
  - 2026-03-05: 15 min (10:14–10:28)
  - 2026-05-14: 13 min (several 1–2 min holes around noon)
  - 2026-06-08: 6 min (12:08–12:13)
- Early closes encoded as 210-minute grids: 2025-07-03, 2025-11-28, 2025-12-24, 2026-07-03.
- Prices match official Yahoo 1m closely on the 17-day overlap: median |close| difference **1.8 cents**, mean 2.5 cents, mean relative 0.0032%. Session closes typically within 5–25 cents. Largest single-day close gap: 41.6 cents on 2026-11-05 (a high-volatility day).
- Month-end Dukascopy SPY closes sit on known levels (e.g. 2025-01-31 ≈ 602, 2025-04-30 ≈ 554, 2026-11-10 ≈ 750.00 vs Yahoo 749.94).

QQQ is similar (466 sessions) with one extra bad coverage day: **2026-10-29 misses 106 minutes**. On 2026-11-10 13:00 ET, Yahoo printed a suspicious $10 one-minute spike (high/close 679.35 vs neighboring 669s); Dukascopy stayed near 669.68. Treat that Yahoo bar as a glitch.

GSPC (US 500 CFD) tracks official `^GSPC` within a typical cash/futures basis: overlap mean |close| 0.46 points (0.006%). The CFD also prints on some US holidays, which is why it has 479 session files vs 466 for SPY.

**VIX CFD is not a clean stand-in for CBOE VIX.** Overlap mean relative close error ≈ 4% (up to ~11% on 2026-11-05), and most days are missing many minutes. Use `yahoo/VIX` when official VIX is required.

## Keyless sources that were tried and not used as the long series

- **HF Data Library** (https://hfdatalibrary.com/) — IEX 1m for SPY/QQQ from 2022-03-07 through 2026-11-10, updated daily, CC BY 4.0. The ticker download API requires a free key / verified email. Not used (no signup). Best free-key alternative if official IEX volume is needed for years of 1m data. Academic/research license; their terms say not for trading.
- **HuggingFace `mito0o852/OHLCV-1m`** — monthly all-ticker parquets through **2026-03 only** (~350–460 MB each). Would leave an Apr–Nov 2026 hole. Not downloaded.
- **HuggingFace `syncster-data/us-market-1m-data`** — gated (access form). Batch 4 claims 2021–2026 1m stocks. Not used.
- **HuggingFace `Traders-Lab/TroveLedger`** — no SPY 1m file; QQQ minutes only through 2026-01-22; maintainers warn not to use current intraday files (split adjustment bug).
- Direct `datafeed.dukascopy.com` ticks from this host often timed out; the `dukascopy-node` client succeeded.

## Free-key services (not signed up) if official exchange volume is required

If RVOL must use official share volume for 6+ months of 1m SPY:

| Service | Typical free-tier 1m depth (verify on signup; this was not authenticated) |
|---|---|
| **Alpaca** (free account, IEX feed) | Historical 1m often cited back to ~2016; latest minutes may be delayed/excluded. Best first try for official-ish ETF volume. |
| **Tiingo** (free IEX) | IEX 1m commonly described from ~Aug 2017. |
| **Twelve Data** (free key, tight rate limits) | Intraday history is plan-limited; docs have mentioned 1m from 2020 on paid plans — free depth is shorter. |
| **Polygon / Massive** | Free tier is generally end-of-day only; 1m is a paid plan. |
| **Alpha Vantage** | Compact/free intraday is a short trailing window; long 1m history is premium. |
| **HF Data Library** | Free key, full SPY/QQQ 1m since 2022-03-07, IEX only, research license. |

IBKR delayed 1m remains available on the user's local TWS/Gateway (`archive_1m.py --source ibkr --backfill-days 180`) and was not reachable from this cloud IP.

See `QUALITY_REPORT.json` for machine-readable session counts, gap lists, and overlap stats.
