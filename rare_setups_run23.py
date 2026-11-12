"""Run 23. One pre-registered replication. Nothing is retuned.

The rule is the round-20 VVIX blowoff, unchanged:
VVIX close is at least 10% above the prior close and VIX close is at
least 5% above the prior close. On a 5-minute book the entry was 18:00
ET and the exit was the 15:55 close two cash sessions later.

Where that clock is not available, the translation fixed here is: buy
the next session's open and sell the close of the session after that.
That is the next open, and the same exit date as the original rule when
the calendars match.

The 2022-2026 S&P result is the discovery sample. It is not in the
confirmation pool. The pool is:
- S&P 500, Yahoo ^GSPC, entries from 2007-01-01 through 2017-12-31
- iShares Russell 2000, Yahoo IWM, full history
- Germany 40, Dukascopy deuidxeur daily bid (history starts 2013-09-30)
- Japan 200, Dukascopy jpnidxjpy daily bid
- EU Stocks 50, Dukascopy eusidxeur daily bid (history starts 2014-06-01)
- FTSE 100, Dukascopy gbridxgbp daily bid

The signal is Yahoo ^VVIX and ^VIX for every market. Cost is 0.02% of
the entry price each way at 1x and 0.04% round trip at 2x, so the
markets can be pooled. A same-market trade is skipped until its exit.

The confirmation bar, fixed here, is the pooled 2x sample: at least 15
trades, expectancy interval lower bound above 0, profit factor above
1.5, more than 60% of active years positive, standalone one-sided p
below 0.05, and at least three markets with a positive 2x mean and at
least 10 trades. The p-value recenters the day-clustered returns and
asks how often a zero-mean bootstrap reaches the observed mean. Days
are the US signal dates, so markets that share a signal are resampled
together. This is one hypothesis, not a new search.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DISCOVERY_START = date(2022, 1, 1)
EARLY_END = date(2017, 12, 31)
EARLY_START = date(2007, 1, 1)
COST_2X = 0.0004
COST_1X = 0.0002


def yahoo_frame(ticker: str) -> pd.DataFrame:
    data = yf.download(ticker, start="2006-01-01", progress=False, auto_adjust=False, threads=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    frame = data[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    return frame.sort_index()[~frame.index.duplicated(keep="last")]


def dukascopy_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.index = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    frame = frame.rename(columns=str.lower)[["open", "high", "low", "close"]]
    return frame.sort_index()[~frame.index.duplicated(keep="last")]


def sessions(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame[frame.index.weekday < 5].dropna()
    previous = frame["close"].shift()
    frozen = (frame["high"] == frame["low"]) & (frame["open"] == frame["close"]) & (frame["open"] == previous)
    return frame.loc[~frozen.fillna(False)]


def signal_dates(vix: pd.Series, vvix: pd.Series) -> list[date]:
    aligned = pd.concat({"vix": vix, "vvix": vvix}, axis=1).dropna().sort_index()
    flag = (aligned["vvix"].pct_change(fill_method=None) >= 0.10) & (aligned["vix"].pct_change(fill_method=None) >= 0.05)
    return [stamp.date() for stamp in aligned.index[flag.fillna(False)]]


def market_trades(frame: pd.DataFrame, signals: list[date]) -> list[dict]:
    book = sessions(frame)
    days = [stamp.date() for stamp in book.index]
    rows = []
    exit_day = date(1900, 1, 1)
    for sig in signals:
        entry_i = next((i for i, day in enumerate(days) if day > sig), None)
        if entry_i is None or entry_i + 1 >= len(days):
            continue
        entry_day = days[entry_i]
        if entry_day <= exit_day:
            continue
        exit_i = entry_i + 1
        entry_px = float(book["open"].iloc[entry_i])
        exit_px = float(book["close"].iloc[exit_i])
        if entry_px <= 0 or not np.isfinite(entry_px) or not np.isfinite(exit_px):
            continue
        rows.append({
            "signal": sig,
            "day": entry_day,
            "year": entry_day.year,
            "gross_return": exit_px / entry_px - 1,
            "entry": entry_px,
            "exit": exit_px,
        })
        exit_day = days[exit_i]
    return rows


def with_cost(trades: list[dict], cost: float) -> list[dict]:
    out = []
    for row in trades:
        item = dict(row)
        item["net"] = row["gross_return"] - cost
        out.append(item)
    return out


def profit_factor(nets: np.ndarray) -> float | None:
    wins = nets[nets > 0].sum()
    losses = nets[nets < 0].sum()
    if losses < 0 and wins > 0:
        return float(wins / abs(losses))
    if losses == 0 and wins > 0:
        return None
    return 0.0


def year_rate(trades: list[dict]) -> tuple[float, list[dict]]:
    buckets: dict[int, float] = {}
    for row in trades:
        buckets[row["year"]] = buckets.get(row["year"], 0.0) + row["net"]
    years = [{"year": year, "total": round(total, 6)} for year, total in sorted(buckets.items())]
    if not years:
        return 0.0, years
    return sum(row["total"] > 0 for row in years) / len(years), years


def cluster_bootstrap(trades: list[dict], draws: int = 1000, seed: int = 16) -> dict:
    grouped: dict[date, list[float]] = {}
    for row in trades:
        grouped.setdefault(row["signal"], []).append(row["net"])
    keys = list(grouped)
    observed = float(np.mean([value for values in grouped.values() for value in values]))
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    nulls = np.empty(draws)
    centered = {key: [value - observed for value in values] for key, values in grouped.items()}
    for draw in range(draws):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        sample = [value for i in pick for value in grouped[keys[i]]]
        null = [value for i in pick for value in centered[keys[i]]]
        means[draw] = float(np.mean(sample)) if sample else np.nan
        nulls[draw] = float(np.mean(null)) if null else np.nan
    ci = [float(np.nanquantile(means, 0.025)), float(np.nanquantile(means, 0.975))]
    p_value = float(np.nanmean(nulls >= observed))
    return {"mean": observed, "ci": ci, "p_value": p_value, "draws": draws}


def summarize_market(name: str, trades: list[dict]) -> dict:
    nets = np.array([row["net"] for row in trades], dtype=float)
    rate, years = year_rate(trades)
    pf = profit_factor(nets) if len(nets) else None
    boot = cluster_bootstrap(trades) if len(trades) >= 2 else {"mean": None, "ci": [None, None], "p_value": 1.0}
    return {
        "market": name,
        "trades": int(len(trades)),
        "win_rate": None if len(nets) == 0 else round(float(np.mean(nets > 0)), 4),
        "expectancy": None if len(nets) == 0 else round(float(np.mean(nets)), 6),
        "expectancy_ci": [None if value is None else round(value, 6) for value in boot["ci"]],
        "profit_factor": None if pf is None else round(pf, 4),
        "years_positive": round(rate, 4),
        "years": years,
        "standalone_p": round(boot["p_value"], 4),
    }


def passes(stats: dict, positive_markets: int) -> bool:
    ci = stats.get("expectancy_ci") or [None, None]
    pf = stats.get("profit_factor")
    return bool(
        stats.get("trades", 0) >= 15
        and ci[0] is not None and ci[0] > 0
        and pf is not None and pf > 1.5
        and (stats.get("years_positive") or 0) > 0.60
        and (stats.get("standalone_p") or 1) < 0.05
        and positive_markets >= 3
    )


def main() -> None:
    print("PRE-REGISTERED vvix_blowoff replication")
    print(" signal VVIX pct_change >= 0.10 and VIX pct_change >= 0.05")
    print(" daily entry next open, exit the following close")
    print(" pool excludes S&P entries on or after 2018-01-01")
    print(" bar: 2x CI lower > 0, PF > 1.5, years > 60%, n >= 15, standalone p < 0.05, 3 markets positive", flush=True)
    vix = yahoo_frame("^VIX")["close"]
    vvix = yahoo_frame("^VVIX")["close"]
    signals = signal_dates(vix, vvix)
    print("SIGNALS", len(signals), signals[0], signals[-1], flush=True)
    markets = {
        "spx_yahoo": yahoo_frame("^GSPC"),
        "iwm_yahoo": yahoo_frame("IWM"),
        "dax_dukascopy": dukascopy_frame(Path("/tmp/rare_data/external/intl/deuidxeur-d1.csv")),
        "nikkei_dukascopy": dukascopy_frame(Path("/tmp/rare_data/external/intl/jpnidxjpy-d1.csv")),
        "stoxx_dukascopy": dukascopy_frame(Path("/tmp/rare_data/external/intl/eusidxeur-d1.csv")),
        "ftse_dukascopy": dukascopy_frame(Path("/tmp/rare_data/external/intl/gbridxgbp-d1.csv")),
    }
    priced = {}
    for name, frame in markets.items():
        rows = with_cost(market_trades(frame, signals), COST_2X)
        if name == "spx_yahoo":
            rows = [row for row in rows if EARLY_START <= row["day"] <= EARLY_END]
        priced[name] = rows
        print("LOCKED", name, "trades", len(rows), "first", frame.index.min().date(), "last", frame.index.max().date(), flush=True)
    discovery = with_cost(market_trades(markets["spx_yahoo"], signals), COST_2X)
    discovery = [row for row in discovery if row["day"] >= DISCOVERY_START]
    per_market = [summarize_market(name, rows) for name, rows in priced.items()]
    pooled = [row for rows in priced.values() for row in rows]
    pooled_stats = summarize_market("pooled_confirmation", pooled)
    positive = sum(1 for row in per_market if (row["trades"] or 0) >= 10 and (row["expectancy"] or 0) > 0)
    pooled_stats["positive_markets_min10"] = positive
    pooled_stats["passes"] = passes(pooled_stats, positive)
    # Point-cost view of the early S&P sample, not used in the pool decision.
    early_points = []
    for row in priced["spx_yahoo"]:
        points = (row["exit"] - row["entry"]) - 2.0
        early_points.append(points)
    payload = {
        "rule": "VVIX close/prior-1 >= 0.10 and VIX close/prior-1 >= 0.05. Next session open to the following close. One position per market.",
        "confirmation_bar": "Pooled 2x return CI lower > 0, PF > 1.5, years_positive > 0.60, trades >= 15, day-cluster standalone p < 0.05, at least 3 markets with positive 2x mean and >= 10 trades. Discovery S&P 2022-2026 is excluded.",
        "cost_2x": "0.04% of entry price, round trip",
        "signals": len(signals),
        "markets": per_market,
        "pooled": pooled_stats,
        "discovery_spx_2022_2026_not_in_pool": {
            "trades": len(discovery),
            "mean_2x_return": None if not discovery else round(float(np.mean([row["net"] for row in discovery])), 6),
        },
        "early_spx_point_pnl_after_2_points": {
            "trades": len(early_points),
            "mean_points": None if not early_points else round(float(np.mean(early_points)), 4),
        },
        "blocked": {
            "fred": "fred.stlouisfed.org timed out on WALCL, RRPONTSYD, WTREGEN, BAMLH0A0HYM2, NFCI and T10Y2Y after three attempts on both the csv and txt endpoints.",
            "put_call": "Yahoo ^PCCE and ^CPCE are empty. The Cboe put/call CSVs still end on 2019-10-04.",
        },
        "passes_confirmation_bar": pooled_stats["passes"],
        "live_default": "legacy",
    }
    Path("artifacts/rare_setups/run23.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("POOLED", pooled_stats["trades"], pooled_stats["expectancy"], pooled_stats["expectancy_ci"], "pf", pooled_stats["profit_factor"], "years", pooled_stats["years_positive"], "p", pooled_stats["standalone_p"], "markets+", positive)
    print("PASS", pooled_stats["passes"])
    for row in per_market:
        print(row["market"], row["trades"], row["win_rate"], row["expectancy"], row["expectancy_ci"], row["profit_factor"], row["years_positive"], row["standalone_p"])


if __name__ == "__main__":
    main()
