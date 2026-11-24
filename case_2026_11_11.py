"""Case study for the 2026-11-11 SPX drop, then one locked archive test.

Nov 11 is the anecdote that suggested the rule. It is not inside the
train, validation, or test split. The archive ends 2026-11-10. The six
exhaustion configs below were written after the 15-minute forensics and
are not changed after the test numbers.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from research_1m_lead import legacy_signals
from trend_24h_study import (
    find_events,
    load_ohlc,
    ml_signals,
    prepare_features,
    resample_bars,
    split_60_20_20,
)

COST = 0.5
TOP = 7647.20
DROP_LOW = 7619.94
ARCHIVE_END = date(2026, 11, 10)


def load_yahoo(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("America/New_York")
    else:
        frame.index = frame.index.tz_convert("America/New_York")
    frame = frame.rename(columns={col: col.capitalize() for col in frame.columns})
    return frame.sort_index()


def load_dukascopy_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return frame.rename(columns={col: col.capitalize() for col in frame.columns})


def five_minute(frame: pd.DataFrame) -> pd.DataFrame:
    bars = frame.resample("5min", label="left", closed="left").agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"), Volume=("Volume", "sum")
    )
    return bars.dropna(subset=["Close"])


def legacy_on(frame: pd.DataFrame, **kwargs) -> list[dict]:
    work = frame.copy()
    if work.index.tz is not None:
        work.index = work.index.tz_convert("UTC")
    if "Volume" not in work:
        work["Volume"] = 0.0
    return legacy_signals(work, **kwargs)


def first_in_window(signals: list[dict], start, end, side: str) -> dict | None:
    rows = []
    for signal in signals:
        stamp = signal["bar_end"]
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        stamp = stamp.tz_convert("America/New_York")
        if start <= stamp <= end and signal["direction"] == side:
            rows.append((stamp, signal))
    if not rows:
        return None
    rows.sort(key=lambda item: item[0])
    return {"time": rows[0][0], "signal": rows[0][1]}


def keltner_signals(frame: pd.DataFrame, jpy: pd.DataFrame) -> list[dict]:
    bars = five_minute(frame)
    close = bars["Close"]
    ema = close.ewm(span=20, adjust=False).mean()
    atr = (bars["High"] - bars["Low"]).rolling(14).mean()
    upper = ema + 2 * atr
    lower = ema - 2 * atr
    jpy_ret = jpy["Close"].pct_change(30).reindex(bars.index, method="ffill", tolerance=pd.Timedelta("10min"))
    out = []
    prev_above = False
    prev_below = False
    for ts, row in bars.iterrows():
        if not np.isfinite(upper.get(ts, np.nan)):
            continue
        above = row["Close"] > upper.get(ts)
        below = row["Close"] < lower.get(ts)
        ret = jpy_ret.get(ts, np.nan)
        end = ts + pd.Timedelta(minutes=5)
        if above and not prev_above and np.isfinite(ret) and ret >= 0.0003:
            out.append({"bar_end": end, "direction": "BULLISH", "price": float(row["Close"]), "atr": float(atr.get(ts))})
        if below and not prev_below and np.isfinite(ret) and ret <= -0.0003:
            out.append({"bar_end": end, "direction": "BEARISH", "price": float(row["Close"]), "atr": float(atr.get(ts))})
        prev_above, prev_below = above, below
    return out


def qqq_lead(spy: pd.DataFrame, qqq: pd.DataFrame) -> list[dict]:
    left = five_minute(spy)["Close"]
    right = five_minute(qqq)["Close"].reindex(left.index, method="ffill", tolerance=pd.Timedelta("10min"))
    spy_ret = left.pct_change(1)
    qqq_ret = right.pct_change(1).shift(1)
    out = []
    for ts, qret in qqq_ret.items():
        sret = spy_ret.get(ts, np.nan)
        if not np.isfinite(qret) or not np.isfinite(sret):
            continue
        end = ts + pd.Timedelta(minutes=5)
        if qret >= 0.0008 and 0 <= sret <= 0.0006:
            out.append({"bar_end": end, "direction": "BULLISH", "price": float(left.get(ts))})
        if qret <= -0.0008 and -0.0006 <= sret <= 0:
            out.append({"bar_end": end, "direction": "BEARISH", "price": float(left.get(ts))})
    return out


def vix_spike(index: pd.DataFrame, vix: pd.DataFrame, jump: float) -> list[dict]:
    """Short when VIX has already risen `jump` over 5 minutes. Known at that close."""
    price = five_minute(index)["Close"]
    vol = five_minute(vix)["Close"].reindex(price.index, method="ffill", tolerance=pd.Timedelta("10min"))
    change = vol.pct_change(1)
    out = []
    for ts, value in change.items():
        if np.isfinite(value) and value >= jump:
            out.append({"bar_end": ts + pd.Timedelta(minutes=5), "direction": "BEARISH", "price": float(price.get(ts)), "vix_jump": float(value)})
        if np.isfinite(value) and value <= -jump:
            out.append({"bar_end": ts + pd.Timedelta(minutes=5), "direction": "BULLISH", "price": float(price.get(ts)), "vix_jump": float(value)})
    return out


def breadth_break(index: pd.DataFrame, names: dict[str, pd.DataFrame]) -> list[dict]:
    price = five_minute(index)["Close"]
    weak = []
    for frame in names.values():
        close = five_minute(frame)["Close"].reindex(price.index, method="ffill", tolerance=pd.Timedelta("10min"))
        weak.append(close.pct_change(3) < 0)
    panel = pd.concat(weak, axis=1)
    share = panel.mean(axis=1)
    prior = price.rolling(3).max().shift(1)
    out = []
    for ts, frac in share.items():
        if not np.isfinite(frac) or frac < 0.7:
            continue
        if price.get(ts, np.nan) < prior.get(ts, np.nan):
            out.append({"bar_end": ts + pd.Timedelta(minutes=5), "direction": "BEARISH", "price": float(price.get(ts)), "weak_share": float(frac)})
    return out


def points_left(side: str, alert_price: float, extreme: float) -> float | None:
    if alert_price is None or not np.isfinite(alert_price):
        return None
    if side == "BEARISH":
        return round(alert_price - extreme, 2)
    return round(extreme - alert_price, 2)


def stopped(path: pd.DataFrame, when, side: str, alert_price: float, stop_price: float, minutes=30) -> bool:
    if path.empty or when is None:
        return False
    after = path.loc[(path.index > when) & (path.index <= when + pd.Timedelta(minutes=minutes))]
    if after.empty:
        return False
    if side == "BEARISH":
        return bool((after["High"] >= stop_price).any())
    return bool((after["Low"] <= stop_price).any())


def rth_mask(index: pd.DatetimeIndex) -> np.ndarray:
    local = index.tz_convert("America/New_York")
    minutes = local.hour * 60 + local.minute
    return (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)


def exhaustion_signals(high, low, close, ts, ny_dates, minutes, vix, gate: float, kind: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Short after an extended up day fails, and the long mirror. Decision index, side, stop price."""
    n = len(close)
    hist = None
    if kind == "macd":
        series = pd.Series(close)
        macd = series.ewm(span=12, adjust=False).mean() - series.ewm(span=26, adjust=False).mean()
        hist = (macd - macd.ewm(span=9, adjust=False).mean()).to_numpy()
    decisions, sides, stops = [], [], []
    i = 0
    while i < n:
        day = ny_dates[i]
        j = i
        while j < n and ny_dates[j] == day:
            j += 1
        prior = None
        k = i - 1
        while k >= 0:
            if 9 * 60 + 30 <= minutes[k] < 16 * 60:
                prior = close[k]
                break
            if ny_dates[k] != day and minutes[k] < 9 * 60 + 30 and prior is not None:
                break
            k -= 1
        # prior RTH close is the last RTH bar of the previous day
        prior = None
        k = i - 1
        while k >= 0 and ny_dates[k] == day:
            k -= 1
        while k >= 0:
            if 9 * 60 + 30 <= minutes[k] < 16 * 60:
                prior = close[k]
                break
            k -= 1
        if prior is None or prior <= 0:
            i = j
            continue
        session_high = -np.inf
        session_low = np.inf
        last_signal = -10**9
        for t in range(i, j):
            if not (9 * 60 + 30 <= minutes[t] < 16 * 60):
                continue
            prev_high = session_high
            prev_low = session_low
            session_high = max(session_high, high[t])
            session_low = min(session_low, low[t])
            day_up = close[t] / prior - 1
            if t - last_signal < 20 or t < i + 20:
                continue
            fired = 0
            stop_px = np.nan
            if kind == "failed":
                if t + 5 >= j:
                    continue
                level = np.max(high[t - 15:t]) if t - i >= 15 else np.nan
                if not np.isfinite(level):
                    continue
                pushed = high[t] > prev_high and high[t] > level and day_up >= gate
                if pushed:
                    for q in range(t + 1, min(t + 6, j)):
                        if close[q] < level:
                            fired = -1
                            stop_px = high[t]
                            t = q
                            break
                level_dn = np.min(low[max(i, t - 15):t]) if t - i >= 15 else np.nan
                dumped = np.isfinite(level_dn) and low[t] < prev_low and low[t] < level_dn and day_up <= -gate
                if fired == 0 and dumped:
                    for q in range(t + 1, min(t + 6, j)):
                        if close[q] > level_dn:
                            fired = 1
                            stop_px = low[t]
                            t = q
                            break
            elif kind == "macd" and hist is not None:
                window = close[t - 20:t]
                if day_up >= gate and close[t] >= np.max(window) and hist[t] < 0:
                    fired = -1
                    stop_px = np.max(high[t - 5:t + 1])
                if day_up <= -gate and close[t] <= np.min(window) and hist[t] > 0:
                    fired = 1
                    stop_px = np.min(low[t - 5:t + 1])
            elif kind == "vix" and vix is not None and t >= 15:
                base = vix[t - 15]
                if np.isfinite(base) and base > 0 and np.isfinite(vix[t]):
                    vix_ret = vix[t] / base - 1
                    window = close[t - 20:t]
                    if day_up >= gate and close[t] >= np.max(window) and vix_ret >= 0.003:
                        fired = -1
                        stop_px = np.max(high[t - 5:t + 1])
                    if day_up <= -gate and close[t] <= np.min(window) and vix_ret <= -0.003:
                        fired = 1
                        stop_px = np.min(low[t - 5:t + 1])
            if fired:
                decisions.append(t)
                sides.append(fired)
                stops.append(stop_px)
                last_signal = t
        i = j
    return np.asarray(decisions, dtype=int), np.asarray(sides, dtype=int), np.asarray(stops, dtype=float)


def simulate_exhaustion(open_, high, low, close, ts, ny_dates, decision, side, stop_px, target: float):
    trades = []
    busy = np.datetime64("1970-01-01")
    for dec, sgn, stop in zip(decision, side, stop_px):
        entry_i = int(dec) + 1
        if entry_i >= len(close) or ts[entry_i] <= busy:
            continue
        if ny_dates[entry_i] != ny_dates[int(dec)]:
            continue
        quote = float(open_[entry_i])
        entry = quote + sgn * COST
        risk_stop = float(stop)
        limit = quote + sgn * target * quote
        exit_price = None
        exit_i = entry_i
        deadline = ts[entry_i] + np.timedelta64(30, "m")
        for j in range(entry_i, len(close)):
            if ts[j] > deadline or ny_dates[j] != ny_dates[entry_i]:
                break
            exit_i = j
            if sgn < 0 and high[j] >= risk_stop:
                exit_price = risk_stop + COST
                break
            if sgn > 0 and low[j] <= risk_stop:
                exit_price = risk_stop - COST
                break
            if sgn < 0 and low[j] <= limit:
                exit_price = limit + COST
                break
            if sgn > 0 and high[j] >= limit:
                exit_price = limit - COST
                break
        if exit_price is None:
            exit_price = float(close[exit_i] - sgn * COST)
        pnl = sgn * (exit_price - entry)
        risk = abs(quote - risk_stop)
        trades.append({
            "pnl": float(pnl), "r": float(pnl / risk) if risk > 0 else 0.0,
            "day": ny_dates[entry_i], "entry_ts": pd.Timestamp(ts[entry_i], tz="UTC"),
            "side": int(sgn), "entry": entry,
        })
        busy = ts[exit_i]
    return trades


def summarize(trades, sessions):
    if not trades:
        return {"trades": 0, "expectancy": None, "expectancy_ci": None, "profit_factor": None, "win_rate": None, "trades_per_session": 0}
    pnls = np.array([item["pnl"] for item in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    grouped = {}
    for item in trades:
        grouped.setdefault(item["day"], []).append(item["pnl"])
    rng = np.random.default_rng(16)
    samples = []
    for _ in range(500):
        chosen = rng.choice(len(sessions), size=len(sessions), replace=True)
        pool = [pnl for k in chosen for pnl in grouped.get(sessions[k], ())]
        if pool:
            samples.append(float(np.mean(pool)))
    ci = None if len(samples) < 20 else [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]
    pf = None
    if losses.size and wins.size:
        pf = float(wins.sum() / abs(losses.sum()))
    return {
        "trades": int(len(trades)),
        "trades_per_session": round(len(trades) / max(1, len(sessions)), 4),
        "win_rate": round(float(np.mean(pnls > 0)), 4),
        "expectancy": round(float(pnls.mean()), 4),
        "expectancy_ci": ci,
        "profit_factor": None if pf is None else round(pf, 4),
        "avg_win": round(float(wins.mean()), 4) if wins.size else None,
        "avg_loss": round(float(losses.mean()), 4) if losses.size else None,
    }


def configs():
    return [
        {"name": "failed_high_1pct", "kind": "failed", "gate": 0.01, "target": 0.0025},
        {"name": "failed_high_0.75pct", "kind": "failed", "gate": 0.0075, "target": 0.0025},
        {"name": "failed_high_1pct_target35", "kind": "failed", "gate": 0.01, "target": 0.0035},
        {"name": "macd_hist_1pct", "kind": "macd", "gate": 0.01, "target": 0.0025},
        {"name": "macd_hist_0.75pct", "kind": "macd", "gate": 0.0075, "target": 0.0025},
        {"name": "vixcfd_div_1pct", "kind": "vix", "gate": 0.01, "target": 0.0025},
    ]


def archive_pass(usa: pd.DataFrame, vix: pd.DataFrame) -> dict:
    ny = usa.index.tz_convert("America/New_York")
    # Keep the case day out of the split.
    keep = np.array([stamp.date() <= ARCHIVE_END for stamp in ny])
    usa = usa.loc[keep]
    ny = usa.index.tz_convert("America/New_York")
    days = sorted({stamp.date() for stamp in ny})
    parts = split_60_20_20(days)
    high = usa["High"].to_numpy(float)
    low = usa["Low"].to_numpy(float)
    close = usa["Close"].to_numpy(float)
    open_ = usa["Open"].to_numpy(float)
    ts = usa.index.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]")
    minutes = np.array([stamp.hour * 60 + stamp.minute for stamp in ny])
    ny_dates = np.array([stamp.date() for stamp in ny], dtype=object)
    vix_aligned = vix["Close"].reindex(usa.index, method="ffill", tolerance=pd.Timedelta("15min")).to_numpy(float) if vix is not None else None
    selection = parts["train"] + parts["validation"]
    daily = np.zeros((len(selection), 6))
    pos = {day: i for i, day in enumerate(selection)}
    sets = {name: set(rows) for name, rows in parts.items()}
    rows = []
    cached = []
    for number, cfg in enumerate(configs()):
        decision, side, stops = exhaustion_signals(high, low, close, ts, ny_dates, minutes, vix_aligned, cfg["gate"], cfg["kind"])
        trades = simulate_exhaustion(open_, high, low, close, ts, ny_dates, decision, side, stops, cfg["target"])
        cached.append(trades)
        grouped = {name: [] for name in parts}
        for trade in trades:
            for name, pool in sets.items():
                if trade["day"] in pool:
                    grouped[name].append(trade)
                    break
            if trade["day"] in pos:
                daily[pos[trade["day"]], number] += trade["pnl"]
        train_m = summarize(grouped["train"], parts["train"])
        val_m = summarize(grouped["validation"], parts["validation"])
        eligible = bool(
            train_m["trades"] >= 30 and val_m["trades"] >= 15
            and (train_m["expectancy"] or -1) > 0 and (val_m["expectancy"] or -1) > 0
            and ((val_m["profit_factor"] is None) or val_m["profit_factor"] > 1)
        )
        rows.append({"name": cfg["name"], "eligible": eligible, "train": train_m, "validation": val_m, "params": cfg})
        print(cfg["name"], "train", train_m["expectancy"], "val", val_m["expectancy"], "eligible", eligible, flush=True)
    pool = [row for row in rows if row["eligible"]]
    pool.sort(key=lambda row: (row["validation"]["expectancy"], row["validation"]["profit_factor"] or 0), reverse=True)
    candidate = pool[0] if pool else None
    reality = {"survives": False, "p_value": 1.0}
    dsr = {"survives": False, "dsr": 0.0}
    if candidate is not None:
        col = next(i for i, row in enumerate(rows) if row["name"] == candidate["name"])
        reality = whites_reality_check(daily, float(daily[:, col].mean()))
        dsr = deflated_sharpe_of(daily[:, col], deflated_sharpe(daily, len(configs()))["sr_star"])
    test_rows = []
    for cfg, trades in zip(configs(), cached):
        test_trades = [trade for trade in trades if trade["day"] in sets["test"]]
        test_rows.append({"name": cfg["name"], "test": summarize(test_trades, parts["test"])})
    return {
        "split": {name: [day.isoformat() for day in days_] for name, days_ in parts.items()},
        "split_counts": {name: len(days_) for name, days_ in parts.items()},
        "configs": len(configs()),
        "rows": rows,
        "candidate": None if candidate is None else candidate["name"],
        "reality_check": reality,
        "deflated_sharpe": {k: v for k, v in dsr.items()},
        "test": test_rows,
        "note": "VIX line uses the Dukascopy volatility CFD, not CBOE VIX. Nov 11 is excluded.",
    }


def main() -> None:
    yahoo = Path("/tmp/case_fetch/yahoo")
    gspc = load_yahoo(yahoo / "GSPC.csv")
    spy = load_yahoo(yahoo / "SPY.csv")
    qqq = load_yahoo(yahoo / "QQQ.csv")
    vix = load_yahoo(yahoo / "VIX.csv")
    vix1d = load_yahoo(yahoo / "VIX1D.csv")
    nvda = load_yahoo(yahoo / "NVDA.csv")
    megas = {name: load_yahoo(yahoo / f"{name}.csv") for name in ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM")}
    usa_new = load_dukascopy_csv(Path("/tmp/case_fetch/dukascopy/usa500idxusd-m1-bid-2026-11-10-2026-11-11T20-22.csv"))
    import yfinance as yf
    jpy = yf.download("JPY=X", interval="1m", period="5d", progress=False, prepost=True)
    if isinstance(jpy.columns, pd.MultiIndex):
        jpy.columns = jpy.columns.get_level_values(0)
    jpy.index = jpy.index.tz_convert("America/New_York")
    jpy = jpy.rename(columns={col: col.capitalize() for col in jpy.columns})

    usa_ny = usa_new.copy()
    usa_ny.index = usa_ny.index.tz_convert("America/New_York")
    drop_start = pd.Timestamp("2026-11-11 13:00", tz="America/New_York")
    drop_end = pd.Timestamp("2026-11-11 14:40", tz="America/New_York")
    rally_start = pd.Timestamp("2026-11-10 17:30", tz="America/New_York")
    rally_end = pd.Timestamp("2026-11-11 11:00", tz="America/New_York")

    detectors = {
        "legacy_spy": legacy_on(spy),
        "legacy_15_2_0.25_0.05": legacy_on(spy, lookback=15, rvol_min=2.0, momentum_pct=0.25, min_distance_atr=0.05),
        "legacy_price_only_usa": legacy_on(usa_ny, require_volume=False),
        "keltner_usdjpy": keltner_signals(usa_ny, jpy),
        "qqq_lead": qqq_lead(spy, qqq),
        "vix_spike": vix_spike(gspc, vix, 0.005),
        "vix1d_spike": vix_spike(gspc, vix1d, 0.01),
        "breadth_weak": breadth_break(gspc, megas),
    }
    # MACD and failed-high on the fresh USA500 path, including Nov 11.
    ny = usa_ny.index
    decision, side, stops = exhaustion_signals(
        usa_ny["High"].to_numpy(float), usa_ny["Low"].to_numpy(float), usa_ny["Close"].to_numpy(float),
        usa_ny.index.tz_convert("UTC").tz_localize(None).to_numpy("datetime64[ns]"),
        np.array([stamp.date() for stamp in ny], dtype=object),
        np.array([stamp.hour * 60 + stamp.minute for stamp in ny]),
        None, 0.01, "macd",
    )
    macd_rows = []
    for dec, sgn in zip(decision, side):
        stamp = ny[int(dec)]
        macd_rows.append({"bar_end": stamp, "direction": "BULLISH" if sgn > 0 else "BEARISH", "price": float(usa_ny["Close"].iloc[int(dec)])})
    detectors["macd_hist_1pct"] = macd_rows
    decision, side, stops = exhaustion_signals(
        usa_ny["High"].to_numpy(float), usa_ny["Low"].to_numpy(float), usa_ny["Close"].to_numpy(float),
        usa_ny.index.tz_convert("UTC").tz_localize(None).to_numpy("datetime64[ns]"),
        np.array([stamp.date() for stamp in ny], dtype=object),
        np.array([stamp.hour * 60 + stamp.minute for stamp in ny]),
        None, 0.01, "failed",
    )
    failed_rows = []
    for dec, sgn in zip(decision, side):
        stamp = ny[int(dec)]
        failed_rows.append({"bar_end": stamp, "direction": "BULLISH" if sgn > 0 else "BEARISH", "price": float(usa_ny["Close"].iloc[int(dec)])})
    detectors["failed_high_1pct"] = failed_rows

    def describe(name, signals, start, end, side, extreme, path):
        hit = first_in_window(signals, start, end, side)
        if hit is None:
            return {"name": name, "alert": None}
        when = hit["time"]
        if path.empty:
            price = float(hit["signal"].get("close", hit["signal"].get("price", np.nan)))
        else:
            pos = path.index.searchsorted(when)
            pos = min(max(pos, 0), len(path) - 1)
            price = float(path["Close"].iloc[pos])
        own = float(hit["signal"].get("close", hit["signal"].get("price", price)))
        after = path.loc[(path.index > when) & (path.index <= when + pd.Timedelta(minutes=30))]
        if after.empty:
            adverse = favorable = None
        elif side == "BEARISH":
            adverse = round(float(after["High"].max() - price), 2)
            favorable = round(float(price - after["Low"].min()), 2)
        else:
            adverse = round(float(price - after["Low"].min()), 2)
            favorable = round(float(after["High"].max() - price), 2)
        return {
            "name": name,
            "time": str(when),
            "direction": side,
            "index_price": round(price, 2),
            "instrument_price": round(own, 2),
            "points_left_to_extreme": points_left(side, price, extreme),
            "adverse_30m": adverse,
            "favorable_30m": favorable,
        }

    drop_path = usa_ny.loc["2026-11-11 13:00":"2026-11-11 15:30"]
    rally_path = usa_ny.loc["2026-11-10 17:00":"2026-11-11 12:00"]
    timeline = {
        "drop": [describe(name, rows, drop_start, drop_end, "BEARISH", DROP_LOW, drop_path) for name, rows in detectors.items()],
        "rally": [describe(name, rows, rally_start, rally_end, "BULLISH", 7575.0, rally_path) for name, rows in detectors.items()],
    }
    print("DROP", json.dumps(timeline["drop"], ensure_ascii=False, indent=2))
    print("RALLY", json.dumps(timeline["rally"], ensure_ascii=False, indent=2))

    print("archive", flush=True)
    usa_all = load_ohlc(Path("/tmp/trend_src/h24/spx_24h/USA500"))
    fresh = usa_new.loc[usa_new.index > usa_all.index.max()]
    usa_all = pd.concat([usa_all, fresh])
    vix_all = load_ohlc(Path("/tmp/trend_src/h24/spx_24h/VIX"))
    report_archive = archive_pass(usa_all, vix_all)
    out = Path("artifacts/case_2026_11_11")
    out.mkdir(parents=True, exist_ok=True)
    payload = {"timeline": timeline, "archive": report_archive, "forensics_note": "Written after the 13:30-13:46 window. VIX cash fell into the high. VIX1D was slightly up. MACD histogram was already negative at the new high."}
    (out / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ARCHIVE CANDIDATE", report_archive["candidate"])


if __name__ == "__main__":
    main()
