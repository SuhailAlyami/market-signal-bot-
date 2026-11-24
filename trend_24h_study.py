"""24-hour trend-onset study on Dukascopy USA500.

The grid in `build_configs` is the whole search. It is fixed before the test
split is scored. Selection uses train and validation only.

Primary label, also fixed: from a one-minute close, price reaches +0.75%
(or -0.75%) within 4 hours and the adverse excursion before that touch stays
inside 0.30%. Other X/H pairs are descriptive counts, not a second search.

Costs: 0.5 USA500 point per side. A second pass at 1.0 point is sensitivity
only. One position at a time. The stop is known at the bar open; the trail
updates afterward. An ambiguous bar that tags both the stop and the target
distance counts as a stop.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check

COST = 0.5
PRIMARY = {"x": 0.0075, "hours": 4, "y": 0.003}
LABEL_GRID = tuple((x, h) for x in (0.005, 0.0075, 0.01) for h in (2, 4, 6))
EMBARGO_H = 6
MEGAS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRKB", "JPM")
SECTORS = ("XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY")


def split_60_20_20(days: list[date]) -> dict[str, list[date]]:
    if len(days) < 15:
        raise ValueError(f"need at least 15 days, found {len(days)}")
    n_test = len(days) // 5
    n_val = len(days) // 5
    return {
        "train": days[: len(days) - n_val - n_test],
        "validation": days[len(days) - n_val - n_test: len(days) - n_test],
        "test": days[-n_test:],
    }


def session_bucket(hour: int, minute: int) -> str:
    hm = hour * 60 + minute
    if hm >= 18 * 60 or hm < 3 * 60:
        return "asia"
    if hm < 8 * 60:
        return "europe"
    if hm < 9 * 60 + 30:
        return "us_pre"
    if hm < 16 * 60:
        return "rth"
    return "after"


def load_ohlc(folder: Path) -> pd.DataFrame:
    files = sorted(Path(folder).glob("*.csv.gz"))
    if not files:
        raise FileNotFoundError(folder)
    frames = [pd.read_csv(path, usecols=["timestamp", "Open", "High", "Low", "Close"]) for path in files]
    frame = pd.concat(frames, ignore_index=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    for col in ("Open", "High", "Low", "Close"):
        frame[col] = frame[col].astype(float)
    return frame


def locate(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        direct = root / name
        if direct.is_dir() and any(direct.glob("*.csv.gz")):
            return direct
        nested = root / "spx_breadth" / name
        if nested.is_dir() and any(nested.glob("*.csv.gz")):
            return nested
    return None


def find_events(high, low, close, times_ns, x: float, y: float, horizon_ns: int) -> list[tuple[int, int, int]]:
    """Non-overlapping trend episodes. Returns (start, side, touch_index)."""
    n = len(close)
    events = []
    i = 0
    while i < n - 2:
        anchor = close[i]
        if not np.isfinite(anchor) or anchor <= 0:
            i += 1
            continue
        up_px = anchor * (1.0 + x)
        floor = anchor * (1.0 - y)
        dn_px = anchor * (1.0 - x)
        ceil = anchor * (1.0 + y)
        deadline = times_ns[i] + horizon_ns
        bull_fail = bear_fail = False
        hit = 0
        touched = i
        j = i + 1
        while j < n and times_ns[j] <= deadline:
            hj = high[j]
            lj = low[j]
            bull_stop = lj < floor
            bull_target = hj >= up_px
            bear_stop = hj > ceil
            bear_target = lj <= dn_px
            if not bull_fail and bull_stop:
                bull_fail = True
            if not bear_fail and bear_stop:
                bear_fail = True
            bull_ok = (not bull_fail) and bull_target
            bear_ok = (not bear_fail) and bear_target
            if bull_ok and bear_ok:
                bull_fail = bear_fail = True
            elif bull_ok:
                hit = 1
                touched = j
                break
            elif bear_ok:
                hit = -1
                touched = j
                break
            if bull_fail and bear_fail:
                break
            j += 1
        if hit:
            events.append((i, hit, touched))
            i = touched + 1
        else:
            i += 1
    return events


def confirmation_remaining(high, low, close, events, confirm=0.0025) -> dict:
    """Share of the move still left once price has already gone `confirm` percent."""
    left = []
    minutes = []
    for start, side, touch in events:
        anchor = close[start]
        if side > 0:
            mfe = float(np.max(high[start + 1: touch + 1]) - anchor)
            level = anchor * (1.0 + confirm)
            hits = np.flatnonzero(close[start + 1: touch + 1] >= level)
        else:
            mfe = float(anchor - np.min(low[start + 1: touch + 1]))
            level = anchor * (1.0 - confirm)
            hits = np.flatnonzero(close[start + 1: touch + 1] <= level)
        if mfe <= 0 or len(hits) == 0:
            continue
        consumed = confirm * anchor / mfe
        left.append(float(1.0 - consumed))
        minutes.append(int(hits[0] + 1))
    if not left:
        return {"events": len(events), "with_confirmation": 0, "median_remaining": None, "median_minutes_to_confirm": None}
    return {
        "events": len(events),
        "with_confirmation": len(left),
        "median_remaining": round(float(np.median(left)), 4),
        "median_minutes_to_confirm": round(float(np.median(minutes)), 2),
    }


def _atr(high, low, close, period=14) -> np.ndarray:
    prev = np.roll(close, 1)
    prev[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    return pd.Series(tr).rolling(period, min_periods=period).mean().to_numpy()


def resample_bars(frame: pd.DataFrame, minutes: int, minimum: int) -> pd.DataFrame:
    rule = f"{minutes}min"
    bars = frame.resample(rule, label="left", closed="left").agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"), n=("Close", "size")
    )
    bars = bars[bars["n"] >= minimum].dropna()
    bars["end"] = bars.index + pd.Timedelta(minutes=minutes)
    return bars


def fresh_break(close: np.ndarray, level: np.ndarray, side: int) -> np.ndarray:
    beyond = (side * (close - level) > 0) & np.isfinite(level)
    previous = np.zeros(len(close), dtype=bool)
    previous[1:] = beyond[:-1]
    return beyond & ~previous


def ema_flip(close: np.ndarray) -> np.ndarray:
    series = pd.Series(close)
    e9 = series.ewm(span=9, adjust=False).mean().to_numpy()
    e21 = series.ewm(span=21, adjust=False).mean().to_numpy()
    e50 = series.ewm(span=50, adjust=False).mean().to_numpy()
    slope = e21 - np.roll(e21, 3)
    slope[:3] = np.nan
    bull = (e9 > e21) & (e21 > e50) & (slope > 0) & (close > e9)
    bear = (e9 < e21) & (e21 < e50) & (slope < 0) & (close < e9)
    bull[1:] = bull[1:] & ~((np.roll(close, 1)[1:] > np.roll(e9, 1)[1:]))
    bear[1:] = bear[1:] & ~((np.roll(close, 1)[1:] < np.roll(e9, 1)[1:]))
    bull[:50] = False
    bear[:50] = False
    return np.where(bull, 1, np.where(bear, -1, 0))


def supertrend_flip(high, low, close, atr, mult=3.0) -> np.ndarray:
    hl2 = (high + low) / 2.0
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    final_u = upper.copy()
    final_l = lower.copy()
    direction = np.ones(len(close))
    for i in range(1, len(close)):
        if not np.isfinite(atr[i]):
            direction[i] = direction[i - 1]
            continue
        if np.isfinite(final_u[i - 1]) and close[i - 1] <= final_u[i - 1]:
            final_u[i] = min(upper[i], final_u[i - 1])
        if np.isfinite(final_l[i - 1]) and close[i - 1] >= final_l[i - 1]:
            final_l[i] = max(lower[i], final_l[i - 1])
        if direction[i - 1] > 0:
            direction[i] = -1 if close[i] < final_l[i] else 1
        else:
            direction[i] = 1 if close[i] > final_u[i] else -1
    flip = np.zeros(len(close), dtype=int)
    flip[1:] = np.where(direction[1:] != direction[:-1], direction[1:], 0)
    return flip


def adx_cross(high, low, close, period=14) -> np.ndarray:
    up = np.diff(high, prepend=high[0])
    down = -np.diff(low, prepend=low[0])
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr = _atr(high, low, close, period)
    alpha = 1.0 / period
    plus_s = pd.Series(plus_dm).ewm(alpha=alpha, adjust=False).mean().to_numpy()
    minus_s = pd.Series(minus_dm).ewm(alpha=alpha, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100 * np.where(atr > 0, plus_s / atr, np.nan)
        minus_di = 100 * np.where(atr > 0, minus_s / atr, np.nan)
        dx = 100 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) > 0, plus_di + minus_di, np.nan)
    adx = pd.Series(dx).ewm(alpha=alpha, adjust=False).mean().to_numpy()
    bull = (adx >= 20) & (plus_di > minus_di)
    bear = (adx >= 20) & (minus_di > plus_di)
    cross_b = bull.copy()
    cross_s = bear.copy()
    cross_b[1:] = bull[1:] & ~bull[:-1]
    cross_s[1:] = bear[1:] & ~bear[:-1]
    return np.where(cross_b, 1, np.where(cross_s, -1, 0))


def simulate(ts, open_, high, low, close, ny_date, decision_i, side, atr, exit_rule, cost):
    trades = []
    if len(decision_i) == 0:
        return trades
    order = np.argsort(decision_i, kind="mergesort")
    decision_i = np.asarray(decision_i)[order]
    side = np.asarray(side)[order]
    atr = np.asarray(atr)[order]
    n = len(close)
    busy_until = np.datetime64("1970-01-01")
    init_mult = exit_rule["init"]
    trail_mult = exit_rule["trail"]
    hours = np.timedelta64(int(exit_rule["hours"] * 60), "m")
    use_be = exit_rule["be"] == 1
    for dec, sgn, risk_atr in zip(decision_i, side, atr):
        dec = int(dec)
        sgn = int(sgn)
        entry_i = dec + 1
        if entry_i >= n or not np.isfinite(risk_atr) or risk_atr <= 0:
            continue
        if ts[entry_i] <= busy_until:
            continue
        if ts[entry_i] - ts[dec] > np.timedelta64(10, "m"):
            continue
        quote = float(open_[entry_i])
        entry = quote + sgn * cost
        risk = float(init_mult * risk_atr)
        stop = quote - sgn * risk
        deadline = ts[entry_i] + hours
        exit_price = None
        exit_i = entry_i
        be_on = False
        extreme = quote
        j = entry_i
        while j < n and ts[j] <= deadline:
            exit_i = j
            if sgn > 0 and open_[j] <= stop:
                exit_price = float(open_[j] - cost)
                break
            if sgn < 0 and open_[j] >= stop:
                exit_price = float(open_[j] + cost)
                break
            hit_stop = (low[j] <= stop) if sgn > 0 else (high[j] >= stop)
            if hit_stop:
                exit_price = float(stop - sgn * cost)
                break
            if sgn > 0:
                extreme = max(extreme, float(high[j]))
                trailed = extreme - trail_mult * float(risk_atr)
                stop = max(stop, trailed)
                if use_be and extreme >= quote + float(risk_atr):
                    be_on = True
            else:
                extreme = min(extreme, float(low[j]))
                trailed = extreme + trail_mult * float(risk_atr)
                stop = min(stop, trailed)
                if use_be and extreme <= quote - float(risk_atr):
                    be_on = True
            if be_on:
                stop = max(stop, quote) if sgn > 0 else min(stop, quote)
            j += 1
        if exit_price is None:
            exit_price = float(close[exit_i] - sgn * cost)
        pnl = sgn * (exit_price - entry)
        trades.append({
            "pnl": float(pnl), "r": float(pnl / risk), "day": ny_date[entry_i],
            "entry_ts": pd.Timestamp(ts[entry_i], tz="UTC"), "exit_ts": pd.Timestamp(ts[exit_i], tz="UTC"),
            "side": sgn, "entry": entry, "exit": float(exit_price), "decision": int(dec),
        })
        busy_until = ts[exit_i]
    return trades


def summarize(trades, sessions, draws=500, seed=16) -> dict:
    if not trades:
        return {
            "trades": 0, "trades_per_session": 0.0, "win_rate": None, "avg_win": None, "avg_loss": None,
            "expectancy": None, "expectancy_ci": None, "expectancy_r": None, "profit_factor": None,
            "max_drawdown": None,
        }
    pnls = np.array([item["pnl"] for item in trades], dtype=float)
    rs = np.array([item["r"] for item in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    equity = np.cumsum(pnls)
    drawdown = float(np.max(np.maximum.accumulate(equity) - equity))
    grouped: dict = {}
    for item in trades:
        grouped.setdefault(item["day"], []).append(item["pnl"])
    ci = None
    if len(sessions) >= 2 and len(grouped) >= 2:
        rng = np.random.default_rng(seed)
        samples = []
        for _ in range(draws):
            chosen = rng.choice(len(sessions), size=len(sessions), replace=True)
            pool = [pnl for k in chosen for pnl in grouped.get(sessions[k], ())]
            if pool:
                samples.append(float(np.mean(pool)))
        if samples:
            ci = [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]
    profit_factor = None
    if losses.size and wins.size:
        profit_factor = float(wins.sum() / abs(losses.sum()))
    elif losses.size:
        profit_factor = 0.0
    return {
        "trades": int(len(trades)),
        "trades_per_session": round(len(trades) / len(sessions), 4) if sessions else None,
        "win_rate": round(float(np.mean(pnls > 0)), 4),
        "avg_win": round(float(wins.mean()), 4) if wins.size else None,
        "avg_loss": round(float(losses.mean()), 4) if losses.size else None,
        "expectancy": round(float(pnls.mean()), 4),
        "expectancy_ci": ci,
        "expectancy_r": round(float(rs.mean()), 4),
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "max_drawdown": round(drawdown, 4),
    }


def monthly(trades) -> list[dict]:
    buckets: dict[str, list[float]] = {}
    for item in trades:
        buckets.setdefault(item["day"].strftime("%Y-%m"), []).append(item["pnl"])
    rows = []
    for month in sorted(buckets):
        values = np.array(buckets[month])
        rows.append({
            "month": month, "trades": int(len(values)), "expectancy": round(float(values.mean()), 4),
            "total": round(float(values.sum()), 4), "win_rate": round(float(np.mean(values > 0)), 4),
        })
    return rows


def month_not_dominated(months: list[dict]) -> bool:
    positive = [row["total"] for row in months if row["total"] > 0]
    if len(positive) < 3:
        return False
    return max(row["total"] for row in months) <= 0.5 * sum(positive)


def eligible(train: dict, validation: dict) -> bool:
    pf = validation["profit_factor"]
    pf_ok = pf is None or pf > 1
    return bool(
        train["trades"] >= 30 and validation["trades"] >= 15
        and (train["expectancy"] or -1) > 0 and (validation["expectancy"] or -1) > 0 and pf_ok
    )


def choose_candidate(rows: list[dict]) -> dict | None:
    pool = [row for row in rows if row["eligible"]]
    if not pool:
        return None
    pool.sort(key=lambda row: (
        row["validation"]["expectancy"],
        row["validation"]["profit_factor"] or 0,
        row["validation"]["trades"],
    ), reverse=True)
    return pool[0]


def promotion_decision(candidate, test_metrics, reality, dsr, months) -> dict:
    if candidate is None or test_metrics is None:
        return {"promote": False, "reason": "no config was positive on both train and validation"}
    ci = test_metrics.get("expectancy_ci") or [None, None]
    pf = test_metrics.get("profit_factor") or 0
    reasons = []
    if not (ci[0] is not None and ci[0] > 0):
        reasons.append("test expectancy interval does not lie above zero")
    if not (pf > 1.2):
        reasons.append("profit factor is not above 1.2")
    if not reality.get("survives"):
        reasons.append("reality check does not clear best-of-N")
    if not dsr.get("survives"):
        reasons.append("deflated Sharpe is below 0.95")
    if not month_not_dominated(months or []):
        reasons.append("test result is dominated by fewer than three positive months or one month")
    return {
        "promote": not reasons,
        "reason": "test expectancy stays positive after costs and the multiple-testing haircut" if not reasons else "; ".join(reasons),
    }


DEFAULT_EXIT = {"init": 1.5, "trail": 3.0, "hours": 6, "be": 0}
EXIT_E2 = {"init": 1.0, "trail": 2.0, "hours": 4, "be": 0}
EXIT_E3 = {"init": 2.0, "trail": 4.0, "hours": 6, "be": 1}


def build_configs() -> list[dict]:
    configs = []
    specs = [
        ("don_5_60", "don", {"tf": 5, "minutes": 60, "k": 0.0}),
        ("don_5_240", "don", {"tf": 5, "minutes": 240, "k": 0.0}),
        ("don_15_180", "don", {"tf": 15, "minutes": 180, "k": 0.0}),
        ("don_15_720", "don", {"tf": 15, "minutes": 720, "k": 0.0}),
        ("don_5_60_buf", "don", {"tf": 5, "minutes": 60, "k": 0.5}),
        ("ema_5", "ema", {"tf": 5}),
        ("ema_15", "ema", {"tf": 15}),
        ("hh_5", "hh", {"tf": 5}),
        ("kel_5", "kel", {"tf": 5}),
        ("kel_15", "kel", {"tf": 15}),
        ("st_5", "st", {"tf": 5}),
        ("adx_5", "adx", {"tf": 5}),
        ("tsm_30_25", "tsm", {"minutes": 30, "threshold": 0.0025}),
        ("tsm_30_40", "tsm", {"minutes": 30, "threshold": 0.0040}),
        ("tsm_90_25", "tsm", {"minutes": 90, "threshold": 0.0025}),
        ("tsm_90_40", "tsm", {"minutes": 90, "threshold": 0.0040}),
        ("vwap_fut", "vwap", {"anchor": "futures"}),
        ("vwap_utc", "vwap", {"anchor": "utc"}),
        ("gap_30", "gap", {}),
        ("eu_open", "europe", {}),
    ]
    for name, kind, params in specs:
        configs.append({"name": name, "kind": kind, "params": params, "exit": dict(DEFAULT_EXIT), "filter": "none"})
    for anchor in ("don_5_60", "ema_5", "tsm_30_25"):
        base = next(cfg for cfg in configs if cfg["name"] == anchor)
        for label, exit_rule in (("e2", EXIT_E2), ("e3", EXIT_E3)):
            configs.append({
                "name": f"{anchor}_{label}", "kind": base["kind"], "params": dict(base["params"]),
                "exit": dict(exit_rule), "filter": "none",
            })
    for anchor in ("don_5_60", "ema_5", "tsm_30_25", "kel_5"):
        base = next(cfg for cfg in configs if cfg["name"] == anchor)
        for filt in ("breadth70", "tech_lead", "dxy_opp", "tlt_opp", "usdjpy_same"):
            configs.append({
                "name": f"{anchor}_{filt}", "kind": base["kind"], "params": dict(base["params"]),
                "exit": dict(DEFAULT_EXIT), "filter": filt,
            })
    for threshold in (0.05, 0.10, 0.15, 0.25):
        configs.append({
            "name": f"ml_{threshold:.2f}", "kind": "ml", "params": {"threshold": threshold},
            "exit": dict(DEFAULT_EXIT), "filter": "none",
        })
    names = [cfg["name"] for cfg in configs]
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate config name")
    return configs


def _pack(decision, side, atr_value, mask):
    decision = np.asarray(decision, dtype=int)
    side = np.asarray(side, dtype=int)
    atr_value = np.asarray(atr_value, dtype=float)
    keep = mask & (side != 0) & np.isfinite(atr_value) & (atr_value > 0)
    return decision[keep], side[keep], atr_value[keep]


def signals_for(cfg, packed) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cfg["kind"] == "ml":
        base = packed["ml"][cfg["params"]["threshold"]]
    else:
        base = packed["base_signals"][cfg["base"]]
    decision, side, atr_value = base
    filt = cfg["filter"]
    if filt == "none":
        return decision, side, atr_value
    feat = packed["feat"]
    keep = np.ones(len(decision), dtype=bool)
    for i, dec in enumerate(decision):
        value = feat[filt][int(dec)]
        sgn = side[i]
        if filt == "breadth70":
            keep[i] = np.isfinite(value) and ((sgn > 0 and value >= 0.70) or (sgn < 0 and value <= 0.30))
        elif filt == "tech_lead":
            keep[i] = np.isfinite(value) and sgn * value >= 0.0005
        elif filt in {"dxy_opp", "tlt_opp"}:
            keep[i] = np.isfinite(value) and sgn * value <= -0.0003
        elif filt == "usdjpy_same":
            keep[i] = np.isfinite(value) and sgn * value >= 0.0003
    return decision[keep], side[keep], atr_value[keep]


def build_rule_signals(market, bars) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    ts = market["ts"]
    close = market["close"]
    high = market["high"]
    low = market["low"]
    out = {}

    def map_bars(frame, side, atr_on_bar):
        if len(frame) == 0 or not np.any(side):
            return np.array([], dtype=int), np.array([], dtype=int), np.array([])
        ends = frame["end"].to_numpy(dtype="datetime64[ns]")
        # Decision bar is the last 1-minute bar strictly before the resampled bar ends.
        pos = np.searchsorted(ts, ends, side="left") - 1
        valid = (pos >= 0) & (pos + 1 < len(ts))
        return _pack(pos[valid], side[valid], atr_on_bar[valid], valid[valid] if False else np.ones(valid.sum(), dtype=bool) if False else side[valid] != 0)

    # The helper above got tangled. Do it plainly.
    def emit(frame, direction, atr_vals):
        ends = frame["end"].to_numpy(dtype="datetime64[ns]")
        pos = np.searchsorted(ts, ends, side="left") - 1
        valid = (pos >= 0) & (pos + 1 < len(ts)) & (direction != 0) & np.isfinite(atr_vals)
        return pos[valid].astype(int), direction[valid].astype(int), atr_vals[valid].astype(float)

    for tf, minutes in ((5, (60, 240)), (15, (180, 720))):
        frame = bars[tf]
        atr = _atr(frame["High"].to_numpy(), frame["Low"].to_numpy(), frame["Close"].to_numpy())
        bar_close = frame["Close"].to_numpy()
        for look_min in minutes:
            length = max(2, look_min // tf)
            prior_high = frame["High"].rolling(length, min_periods=length).max().shift(1).to_numpy()
            prior_low = frame["Low"].rolling(length, min_periods=length).min().shift(1).to_numpy()
            bull = fresh_break(bar_close, prior_high, 1)
            bear = fresh_break(bar_close, prior_low, -1)
            direction = np.where(bull & ~bear, 1, np.where(bear & ~bull, -1, 0))
            key = f"don_{tf}_{look_min}"
            out[key] = emit(frame, direction, atr)
            if tf == 5 and look_min == 60:
                bull_b = fresh_break(bar_close, prior_high + 0.5 * atr, 1)
                bear_b = fresh_break(bar_close, prior_low - 0.5 * atr, -1)
                direction_b = np.where(bull_b & ~bear_b, 1, np.where(bear_b & ~bull_b, -1, 0))
                out["don_5_60_buf"] = emit(frame, direction_b, atr)
        direction = ema_flip(bar_close)
        out[f"ema_{tf}"] = emit(frame, direction, atr)
        if tf == 5:
            prior6 = frame["High"].rolling(6, min_periods=6).max().shift(1).to_numpy()
            low_now = frame["Low"].rolling(6, min_periods=6).min().to_numpy()
            low_prev = frame["Low"].rolling(6, min_periods=6).min().shift(6).to_numpy()
            higher = (low_now > low_prev) & fresh_break(bar_close, prior6, 1)
            lower = (frame["High"].rolling(6, min_periods=6).max().to_numpy() < frame["High"].rolling(6, min_periods=6).max().shift(6).to_numpy()) & fresh_break(bar_close, frame["Low"].rolling(6, min_periods=6).min().shift(1).to_numpy(), -1)
            hh = np.where(higher & ~lower, 1, np.where(lower & ~higher, -1, 0))
            out["hh_5"] = emit(frame, hh, atr)
            mid = pd.Series(bar_close).ewm(span=20, adjust=False).mean().to_numpy()
            kel_up = fresh_break(bar_close, mid + 2 * atr, 1)
            kel_dn = fresh_break(bar_close, mid - 2 * atr, -1)
            out["kel_5"] = emit(frame, np.where(kel_up & ~kel_dn, 1, np.where(kel_dn & ~kel_up, -1, 0)), atr)
            out["st_5"] = emit(frame, supertrend_flip(frame["High"].to_numpy(), frame["Low"].to_numpy(), bar_close, atr), atr)
            out["adx_5"] = emit(frame, adx_cross(frame["High"].to_numpy(), frame["Low"].to_numpy(), bar_close), atr)
        else:
            mid = pd.Series(bar_close).ewm(span=20, adjust=False).mean().to_numpy()
            kel_up = fresh_break(bar_close, mid + 2 * atr, 1)
            kel_dn = fresh_break(bar_close, mid - 2 * atr, -1)
            out["kel_15"] = emit(frame, np.where(kel_up & ~kel_dn, 1, np.where(kel_dn & ~kel_up, -1, 0)), atr)

    # Time-series momentum, decided on 5-minute closes, measured on one-minute bars.
    frame = bars[5]
    atr5 = _atr(frame["High"].to_numpy(), frame["Low"].to_numpy(), frame["Close"].to_numpy())
    ends = frame["end"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(ts, ends, side="left") - 1
    for minutes, threshold in ((30, 0.0025), (30, 0.004), (90, 0.0025), (90, 0.004)):
        direction = np.zeros(len(frame), dtype=int)
        for k, dec in enumerate(pos):
            if dec < minutes or dec + 1 >= len(ts):
                continue
            if ts[dec] - ts[dec - minutes] > np.timedelta64(minutes + 15, "m"):
                continue
            anchor = close[dec - minutes]
            if anchor <= 0:
                continue
            ret = close[dec] / anchor - 1
            adverse_up = (anchor - np.min(low[dec - minutes: dec + 1])) / anchor
            adverse_dn = (np.max(high[dec - minutes: dec + 1]) - anchor) / anchor
            if ret >= threshold and adverse_up <= 0.0015:
                direction[k] = 1
            elif ret <= -threshold and adverse_dn <= 0.0015:
                direction[k] = -1
        bps = int(round(threshold * 10000))
        out[f"tsm_{minutes}_{bps}"] = emit(frame, direction, atr5)

    out["vwap_fut"] = _vwap_signals(market, bars[5], "futures")
    out["vwap_utc"] = _vwap_signals(market, bars[5], "utc")
    out["gap_30"] = _gap_signals(market, bars[5])
    out["eu_open"] = _europe_signals(market, bars[5])
    return out


def _vwap_signals(market, frame, anchor: str):
    ts = market["ts"]
    ny = market["ny"]
    typical = (market["high"] + market["low"] + market["close"]) / 3.0
    if anchor == "futures":
        keys = np.array([stamp.date() + timedelta(days=1) if (stamp.hour * 60 + stamp.minute) >= 18 * 60 else stamp.date() for stamp in ny])
    else:
        keys = np.array([stamp.date() for stamp in pd.DatetimeIndex(ts).tz_localize("UTC")])
    vwap = np.full(len(ts), np.nan)
    above_run = np.zeros(len(ts), dtype=int)
    start = 0
    while start < len(ts):
        end = start + 1
        while end < len(ts) and keys[end] == keys[start]:
            end += 1
        acc = np.cumsum(typical[start:end])
        vwap[start:end] = acc / np.arange(1, end - start + 1)
        run = 0
        for i in range(start, end):
            if market["close"][i] > vwap[i]:
                run += 1
            else:
                run = 0
            above_run[i] = run
        start = end
    atr5 = _atr(frame["High"].to_numpy(), frame["Low"].to_numpy(), frame["Close"].to_numpy())
    ends = frame["end"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(ts, ends, side="left") - 1
    prior_high = pd.Series(market["high"]).rolling(30, min_periods=30).max().shift(1).to_numpy()
    prior_low = pd.Series(market["low"]).rolling(30, min_periods=30).min().shift(1).to_numpy()
    direction = np.zeros(len(frame), dtype=int)
    for k, dec in enumerate(pos):
        if dec < 30 or not np.isfinite(vwap[dec]):
            continue
        if above_run[dec] >= 30 and market["close"][dec] > prior_high[dec] and (dec == 0 or market["close"][dec - 1] <= prior_high[dec - 1]):
            direction[k] = 1
        below = 0
        j = dec
        while j >= 0 and keys[j] == keys[dec] and market["close"][j] < vwap[j]:
            below += 1
            j -= 1
            if below >= 30:
                break
        if below >= 30 and market["close"][dec] < prior_low[dec] and market["close"][dec - 1] >= prior_low[dec - 1]:
            direction[k] = -1 if direction[k] == 0 else 0
    return _emit(ts, frame, direction, atr5)


def _emit(ts, frame, direction, atr_vals):
    ends = frame["end"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(ts, ends, side="left") - 1
    valid = (pos >= 0) & (pos + 1 < len(ts)) & (direction != 0) & np.isfinite(atr_vals)
    return pos[valid].astype(int), direction[valid].astype(int), atr_vals[valid].astype(float)


def _gap_signals(market, frame):
    ts = market["ts"]
    ny = market["ny"]
    hm = np.array([stamp.hour * 60 + stamp.minute for stamp in ny])
    dates = np.array([stamp.date() for stamp in ny])
    rth_close = {}
    for i in range(len(ts)):
        if 9 * 60 + 30 <= hm[i] < 16 * 60:
            rth_close[dates[i]] = market["close"][i]
    atr5 = _atr(frame["High"].to_numpy(), frame["Low"].to_numpy(), frame["Close"].to_numpy())
    direction = np.zeros(len(frame), dtype=int)
    seen = set()
    ends = frame["end"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(ts, ends, side="left") - 1
    ordered = sorted(rth_close)
    prev_for = {}
    for a, b in zip(ordered, ordered[1:]):
        prev_for[b] = rth_close[a]
    for k, dec in enumerate(pos):
        if dec < 0:
            continue
        day = dates[dec]
        minute = hm[dec]
        if not (9 * 60 + 30 <= minute < 9 * 60 + 40) or day in seen or day not in prev_for:
            continue
        prior = prev_for[day]
        if prior <= 0:
            continue
        gap = frame["Open"].iloc[k] / prior - 1
        still = frame["Close"].iloc[k] / prior - 1
        if gap >= 0.003 and still > 0:
            direction[k] = 1
            seen.add(day)
        elif gap <= -0.003 and still < 0:
            direction[k] = -1
            seen.add(day)
    return _emit(ts, frame, direction, atr5)


def _europe_signals(market, frame):
    ts = market["ts"]
    ny = market["ny"]
    hm = np.array([stamp.hour * 60 + stamp.minute for stamp in ny])
    dates = np.array([stamp.date() for stamp in ny])
    ranges = {}
    for i in range(len(ts)):
        if 60 <= hm[i] < 180:
            day = dates[i]
            hi, lo = ranges.get(day, (market["high"][i], market["low"][i]))
            ranges[day] = (max(hi, market["high"][i]), min(lo, market["low"][i]))
    atr5 = _atr(frame["High"].to_numpy(), frame["Low"].to_numpy(), frame["Close"].to_numpy())
    direction = np.zeros(len(frame), dtype=int)
    seen = set()
    ends = frame["end"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(ts, ends, side="left") - 1
    for k, dec in enumerate(pos):
        if dec < 0:
            continue
        day = dates[dec]
        minute = hm[dec]
        if day in seen or day not in ranges or not (180 <= minute < 210):
            continue
        hi, lo = ranges[day]
        if frame["Close"].iloc[k] > hi:
            direction[k] = 1
            seen.add(day)
        elif frame["Close"].iloc[k] < lo:
            direction[k] = -1
            seen.add(day)
    return _emit(ts, frame, direction, atr5)


def _fit_logit(x_train, y_train, l2=2.0):
    pos = max(1, int(np.sum(y_train)))
    weight = np.where(y_train == 1, (len(y_train) - pos) / pos, 1.0)
    design = np.column_stack([np.ones(len(x_train)), x_train])
    weights = np.zeros(design.shape[1])
    for _ in range(18):
        linear = np.clip(design @ weights, -20, 20)
        prob = 1 / (1 + np.exp(-linear))
        hess = weight * prob * (1 - prob)
        grad = design.T @ (weight * (prob - y_train))
        grad[1:] += l2 * weights[1:]
        fisher = design.T @ (design * hess[:, None])
        fisher[1:, 1:] += l2 * np.eye(design.shape[1] - 1)
        step = np.linalg.solve(fisher + 1e-6 * np.eye(design.shape[1]), grad)
        weights -= step
        if np.max(np.abs(step)) < 1e-5:
            break
    return weights


def _predict(weights, features):
    design = np.column_stack([np.ones(len(features)), features])
    linear = np.clip(design @ weights, -20, 20)
    return 1 / (1 + np.exp(-linear))


def attach_base_names(configs, signals):
    alias = {
        "don_5_60": "don_5_60", "don_5_240": "don_5_240", "don_15_180": "don_15_180",
        "don_15_720": "don_15_720", "don_5_60_buf": "don_5_60_buf",
    }
    for cfg in configs:
        if cfg["kind"] == "ml":
            cfg["base"] = None
            continue
        name = cfg["name"]
        for suffix in ("_e2", "_e3", "_breadth70", "_tech_lead", "_dxy_opp", "_tlt_opp", "_usdjpy_same"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        if name not in signals:
            raise KeyError(name)
        cfg["base"] = name


def prepare_features(market, roots, tech: pd.DataFrame) -> dict[str, np.ndarray]:
    index = pd.DatetimeIndex(market["ts"])
    if index.tz is None:
        index = index.tz_localize("UTC")
    usa_ret = pd.Series(market["close"], index=index).pct_change(30)
    tech_ret = tech["Close"].pct_change(30).reindex(index, method="ffill", tolerance=pd.Timedelta("10min"))
    tech_lead = (tech_ret - usa_ret).to_numpy(dtype=float)
    features = {"tech_lead": tech_lead}
    panels = []
    for name in MEGAS + SECTORS:
        folder = locate(name, roots)
        if folder is None:
            continue
        frame = load_ohlc(folder)
        typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3.0
        vwap = typical.rolling(30, min_periods=30).mean()
        above = (frame["Close"] > vwap).astype(float)
        above = above.where(vwap.notna())
        panels.append(above.rename(name))
    if panels:
        panel = pd.concat(panels, axis=1).sort_index()
        frac = panel.mean(axis=1, skipna=True)
        count = panel.notna().sum(axis=1)
        frac = frac.where(count >= 12)
        features["breadth70"] = frac.reindex(index, method="ffill", tolerance=pd.Timedelta("10min")).to_numpy(dtype=float)
    else:
        features["breadth70"] = np.full(len(index), np.nan)
    for key, symbol in (("dxy_opp", "DXY"), ("tlt_opp", "TLT"), ("usdjpy_same", "USDJPY")):
        folder = locate(symbol, roots)
        if folder is None:
            features[key] = np.full(len(index), np.nan)
            continue
        series = load_ohlc(folder)["Close"].pct_change(30)
        features[key] = series.reindex(index, method="ffill", tolerance=pd.Timedelta("10min")).to_numpy(dtype=float)
    return features


def ml_signals(market, bars, events, features, parts):
    frame = bars[5]
    ts = market["ts"]
    ends = frame["end"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(ts, ends, side="left") - 1
    valid = (pos >= 120) & (pos + 1 < len(ts))
    pos = pos[valid]
    close = market["close"]
    ret30 = close[pos] / close[pos - 30] - 1
    ret60 = close[pos] / close[pos - 60] - 1
    ret120 = close[pos] / close[pos - 120] - 1
    atr = _atr(frame["High"].to_numpy(), frame["Low"].to_numpy(), frame["Close"].to_numpy())[valid]
    ema21 = pd.Series(frame["Close"]).ewm(span=21, adjust=False).mean().to_numpy()[valid]
    don_hi = frame["High"].rolling(36, min_periods=36).max().to_numpy()[valid]
    don_lo = frame["Low"].rolling(36, min_periods=36).min().to_numpy()[valid]
    with np.errstate(divide="ignore", invalid="ignore"):
        don_pos = (frame["Close"].to_numpy()[valid] - don_lo) / np.where(don_hi > don_lo, don_hi - don_lo, np.nan)
        dist = frame["Close"].to_numpy()[valid] / ema21 - 1
    ny = market["ny"]
    hours = np.array([ny[i].hour + ny[i].minute / 60 for i in pos])
    columns = np.column_stack([
        ret30, ret60, ret120, dist, don_pos, atr / close[pos],
        np.nan_to_num(features["breadth70"][pos], nan=0.0),
        np.nan_to_num(features["tech_lead"][pos], nan=0.0),
        np.nan_to_num(features["dxy_opp"][pos], nan=0.0),
        np.nan_to_num(features["tlt_opp"][pos], nan=0.0),
        np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24),
    ])
    columns = np.nan_to_num(columns, nan=0.0, posinf=0.0, neginf=0.0)
    days = np.array([ny[i].date() for i in pos])
    train_days = set(parts["train"])
    first_val = pd.Timestamp(parts["validation"][0]).tz_localize("America/New_York")
    embargo = first_val.tz_convert("UTC") - pd.Timedelta(hours=EMBARGO_H)
    train_row = np.array([
        day in train_days and pd.Timestamp(ts[i]).tz_localize("UTC") < embargo
        for day, i in zip(days, pos)
    ])
    start_ns = {event[0]: event[1] for event in events}
    y_bull = np.zeros(len(pos))
    y_bear = np.zeros(len(pos))
    event_times = ts[np.array([event[0] for event in events])] if events else np.array([], dtype="datetime64[ns]")
    event_side = np.array([event[1] for event in events]) if events else np.array([])
    if len(event_times):
        for k, dec in enumerate(pos):
            horizon = ts[dec] + np.timedelta64(60, "m")
            right = np.searchsorted(event_times, horizon, side="right")
            left = np.searchsorted(event_times, ts[dec], side="right")
            if right > left:
                if np.any(event_side[left:right] > 0):
                    y_bull[k] = 1
                if np.any(event_side[left:right] < 0):
                    y_bear[k] = 1
    if train_row.sum() < 100 or y_bull[train_row].sum() < 20 or y_bear[train_row].sum() < 20:
        empty = (np.array([], dtype=int), np.array([], dtype=int), np.array([]))
        return {thr: empty for thr in (0.05, 0.10, 0.15, 0.25)}
    mean = columns[train_row].mean(axis=0)
    std = columns[train_row].std(axis=0)
    std[std < 1e-8] = 1
    scaled = (columns - mean) / std
    up = _fit_logit(scaled[train_row], y_bull[train_row])
    down = _fit_logit(scaled[train_row], y_bear[train_row])
    score = _predict(up, scaled) - _predict(down, scaled)
    packed = {}
    for thr in (0.05, 0.10, 0.15, 0.25):
        choose = np.zeros(len(score), dtype=int)
        choose[score >= thr] = 1
        choose[score <= -thr] = -1
        keep = choose != 0
        packed[thr] = (pos[keep].astype(int), choose[keep].astype(int), atr[keep].astype(float))
    return packed


def largest_recent_moves(market, days: set[date], hours=6) -> list[dict]:
    ts = market["ts"]
    close = market["close"]
    high = market["high"]
    ny = market["ny"]
    mask = np.array([stamp.date() in days for stamp in ny])
    idxs = np.flatnonzero(mask)
    rows = []
    if len(idxs) == 0:
        return rows
    horizon = np.timedelta64(hours, "h")
    for dec in idxs[::15]:
        deadline = ts[dec] + horizon
        end = int(np.searchsorted(ts, deadline, side="right"))
        if end <= dec + 1:
            continue
        peak_i = dec + 1 + int(np.argmax(high[dec + 1: end]))
        points = float(high[peak_i] - close[dec])
        rows.append({
            "start": str(pd.Timestamp(ts[dec])), "peak": str(pd.Timestamp(ts[peak_i])),
            "from": round(float(close[dec]), 2), "to": round(float(high[peak_i]), 2),
            "points": round(points, 2),
        })
    rows.sort(key=lambda row: row["points"], reverse=True)
    return rows[:5]


def pine_source(cfg: dict, promoted: bool) -> str:
    status = "READY" if promoted else "RESEARCH_ONLY"
    kind = cfg["kind"]
    params = cfg["params"]
    exit_rule = cfg["exit"]
    header = f"""//@version=5
indicator("Suhail trend {status}", overlay=true, max_labels_count=50)
// {status}. This is not a promoted live signal unless the header says READY.
// Python rule: {cfg['name']} on Dukascopy USA500 bid. Costs are not taken on the chart.
// Filter in the study: {cfg['filter']}. External breadth is not recomputed here.
// Design timeframe is requested below, so a 1-minute or 5-minute chart shows the same decision.
"""
    tf = params.get("tf", 5)
    body = f"""
tf = "{tf}"
[sigHigh, sigLow, sigClose, sigAtr] = request.security(syminfo.tickerid, tf, [high, low, close, ta.atr(14)], barmerge.gaps_off, barmerge.lookahead_off)
trailMult = {exit_rule['trail']}
initMult = {exit_rule['init']}
"""
    if kind == "don":
        length = max(2, int(params["minutes"]) // int(params["tf"]))
        body += f"""
priorHigh = request.security(syminfo.tickerid, tf, ta.highest(high, {length})[1], barmerge.gaps_off, barmerge.lookahead_off)
priorLow = request.security(syminfo.tickerid, tf, ta.lowest(low, {length})[1], barmerge.gaps_off, barmerge.lookahead_off)
longCond = ta.crossover(sigClose, priorHigh + {params['k']} * sigAtr)
shortCond = ta.crossunder(sigClose, priorLow - {params['k']} * sigAtr)
"""
    elif kind == "ema":
        body += """
[e9, e21, e50] = request.security(syminfo.tickerid, tf, [ta.ema(close, 9), ta.ema(close, 21), ta.ema(close, 50)], barmerge.gaps_off, barmerge.lookahead_off)
longCond = e9 > e21 and e21 > e50 and e21 > e21[3] and ta.crossover(sigClose, e9)
shortCond = e9 < e21 and e21 < e50 and e21 < e21[3] and ta.crossunder(sigClose, e9)
"""
    elif kind == "tsm":
        body += f"""
ret = request.security(syminfo.tickerid, "1", close / close[{params['minutes']}] - 1, barmerge.gaps_off, barmerge.lookahead_off)
longCond = ret >= {params['threshold']} and ret[1] < {params['threshold']}
shortCond = ret <= -{params['threshold']} and ret[1] > -{params['threshold']}
"""
    elif kind == "kel":
        body += """
[mid, up, dn] = request.security(syminfo.tickerid, tf, [ta.ema(close, 20), ta.ema(close, 20) + 2 * ta.atr(14), ta.ema(close, 20) - 2 * ta.atr(14)], barmerge.gaps_off, barmerge.lookahead_off)
longCond = ta.crossover(sigClose, up)
shortCond = ta.crossunder(sigClose, dn)
"""
    elif kind == "st":
        body += """
[stLine, stDir] = request.security(syminfo.tickerid, tf, ta.supertrend(3.0, 10), barmerge.gaps_off, barmerge.lookahead_off)
longCond = stDir < 0 and nz(stDir[1], stDir) > 0
shortCond = stDir > 0 and nz(stDir[1], stDir) < 0
"""
    else:
        body += """
longCond = false
shortCond = false
"""
    body += """
var float extreme = na
var float stop = na
var int dir = 0
if longCond
    dir := 1
    extreme := sigHigh
    stop := sigClose - initMult * sigAtr
if shortCond
    dir := -1
    extreme := sigLow
    stop := sigClose + initMult * sigAtr
if dir == 1
    extreme := math.max(nz(extreme, sigHigh), sigHigh)
    stop := math.max(nz(stop, sigClose), extreme - trailMult * sigAtr)
if dir == -1
    extreme := math.min(nz(extreme, sigLow), sigLow)
    stop := math.min(nz(stop, sigClose), extreme + trailMult * sigAtr)
plot(stop, "ATR stop", color=dir == 1 ? color.teal : color.orange)
alertcondition(longCond, "Trend long", "Trend long")
alertcondition(shortCond, "Trend short", "Trend short")
"""
    return header + body


def run(usa_dir: Path, tech_dir: Path, roots: list[Path], spy_dir: Path | None) -> dict:
    print("loading USA500", flush=True)
    usa = load_ohlc(usa_dir)
    tech = load_ohlc(tech_dir)
    ny = usa.index.tz_convert("America/New_York")
    market = {
        "ts": usa.index.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]"),
        "ny": list(ny),
        "open": usa["Open"].to_numpy(dtype=float),
        "high": usa["High"].to_numpy(dtype=float),
        "low": usa["Low"].to_numpy(dtype=float),
        "close": usa["Close"].to_numpy(dtype=float),
    }
    print(f"bars {len(market['close'])} last {usa.index[-1]} {market['close'][-1]:.2f}", flush=True)
    times_ns = market["ts"].astype("int64")
    days = sorted({stamp.date() for stamp in market["ny"]})
    parts = split_60_20_20(days)
    print("labels", flush=True)
    label_rows = []
    primary_events = None
    for x, hours in LABEL_GRID:
        events = find_events(market["high"], market["low"], market["close"], times_ns, x, PRIMARY["y"], int(hours * 3600 * 1e9))
        buckets = {"asia": 0, "europe": 0, "us_pre": 0, "rth": 0, "after": 0}
        for start, _side, _touch in events:
            stamp = market["ny"][start]
            buckets[session_bucket(stamp.hour, stamp.minute)] += 1
        row = {"x": x, "hours": hours, "y": PRIMARY["y"], "events": len(events), "by_session": buckets}
        if x == PRIMARY["x"] and hours == PRIMARY["hours"]:
            primary_events = events
            row["remaining_after_0.25pct"] = confirmation_remaining(market["high"], market["low"], market["close"], events)
        label_rows.append(row)
        print(f"label {x} {hours}h events {len(events)}", flush=True)
    bars = {5: resample_bars(usa, 5, 3), 15: resample_bars(usa, 15, 8)}
    print("rules", flush=True)
    rule_signals = build_rule_signals(market, bars)
    print("features", flush=True)
    features = prepare_features(market, roots, tech)
    print("model", flush=True)
    ml = ml_signals(market, bars, primary_events, features, parts)
    configs = build_configs()
    attach_base_names(configs, rule_signals)
    packed = {"base_signals": rule_signals, "ml": ml, "feat": features}
    print(f"configs {len(configs)}", flush=True)
    ny_dates = np.array([stamp.date() for stamp in market["ny"]], dtype=object)
    sets = {name: set(days_) for name, days_ in parts.items()}
    selection_days = parts["train"] + parts["validation"]
    daily = np.zeros((len(selection_days), len(configs)))
    sel_pos = {day: i for i, day in enumerate(selection_days)}
    cached = []
    rows = []
    for number, cfg in enumerate(configs):
        decision, side, atr_vals = signals_for(cfg, packed)
        trades = simulate(
            market["ts"], market["open"], market["high"], market["low"], market["close"],
            ny_dates, decision, side, atr_vals, cfg["exit"], COST,
        )
        cached.append(trades)
        grouped = {name: [] for name in parts}
        for trade in trades:
            for name, pool in sets.items():
                if trade["day"] in pool:
                    grouped[name].append(trade)
                    break
            pos = sel_pos.get(trade["day"])
            if pos is not None:
                daily[pos, number] += trade["pnl"]
        train_m = summarize(grouped["train"], parts["train"])
        val_m = summarize(grouped["validation"], parts["validation"])
        rows.append({
            "name": cfg["name"], "kind": cfg["kind"], "params": cfg["params"], "exit": cfg["exit"],
            "filter": cfg["filter"], "eligible": eligible(train_m, val_m), "train": train_m, "validation": val_m,
        })
        if number % 10 == 0:
            print(f"scored {number + 1} {cfg['name']}", flush=True)
    candidate = choose_candidate(rows)
    reality = {"p_value": 1.0, "survives": False}
    dsr = {"dsr": 0.0, "survives": False}
    if candidate is not None:
        col = next(i for i, row in enumerate(rows) if row["name"] == candidate["name"])
        reality = whites_reality_check(daily, float(daily[:, col].mean()))
        sr_star = deflated_sharpe(daily, len(configs))["sr_star"]
        dsr = deflated_sharpe_of(daily[:, col], sr_star)
    test_by_name = {}
    winner_test = winner_months = winner_slip = None
    winner_trades = []
    for cfg, trades in zip(configs, cached):
        test_trades = [trade for trade in trades if trade["day"] in sets["test"]]
        metrics = summarize(test_trades, parts["test"])
        test_by_name[cfg["name"]] = metrics
        if candidate is not None and cfg["name"] == candidate["name"]:
            winner_test = metrics
            winner_months = monthly(test_trades)
            winner_trades = test_trades
            slip = simulate(
                market["ts"], market["open"], market["high"], market["low"], market["close"],
                ny_dates, *signals_for(cfg, packed), cfg["exit"], COST * 2,
            )
            winner_slip = summarize([trade for trade in slip if trade["day"] in sets["test"]], parts["test"])
    decision = promotion_decision(candidate, winner_test, reality, dsr, winner_months)
    ranked = sorted(rows, key=lambda row: (row["validation"]["expectancy"] or -999), reverse=True)
    shortlist = []
    for row in ranked[:12]:
        shortlist.append({
            "name": row["name"], "eligible": row["eligible"], "filter": row["filter"],
            "validation_expectancy": row["validation"]["expectancy"],
            "train_expectancy": row["train"]["expectancy"],
            "test": test_by_name[row["name"]],
        })
    research = candidate or ranked[0]
    recent_days = {day for day in days if day >= date(2026, 11, 1)}
    recent = largest_recent_moves(market, recent_days)
    case_trades = [
        {"entry": str(trade["entry_ts"]), "exit": str(trade["exit_ts"]), "side": trade["side"], "pnl": round(trade["pnl"], 2)}
        for trade in winner_trades if trade["day"] >= date(2026, 11, 1)
    ]
    last_stamp = pd.Timestamp(market["ts"][-1]).tz_localize("UTC")
    report = {
        "coverage": {
            "bars": int(len(market["close"])),
            "first": str(pd.Timestamp(market["ts"][0]).tz_localize("UTC")),
            "last": str(last_stamp),
            "last_price": round(float(market["close"][-1]), 2),
            "note": "Archive request ended 2026-11-11 00:00 UTC. A rally that started after the last bar is not in the file.",
        },
        "protocol": {
            "configs": len(configs),
            "cost_points_per_side": COST,
            "primary_label": PRIMARY,
            "selection": "max validation expectancy among configs with positive train and validation expectancy, validation PF>1, train trades>=30, validation trades>=15",
            "promotion": "test CI lower > 0 at 0.5 point per side, PF>1.2, reality-check p<0.05, deflated Sharpe>=0.95, and at least three positive test months with no single month above half of positive-month profits",
        },
        "split_counts": {name: len(days_) for name, days_ in parts.items()},
        "split": {name: [day.isoformat() for day in days_] for name, days_ in parts.items()},
        "labels": label_rows,
        "candidate": None if candidate is None else {
            "name": candidate["name"], "kind": candidate["kind"], "params": candidate["params"],
            "exit": candidate["exit"], "filter": candidate["filter"],
            "train": candidate["train"], "validation": candidate["validation"],
        },
        "reality_check": reality,
        "deflated_sharpe": {key: value for key, value in dsr.items()},
        "test": winner_test,
        "test_cost_1_point": winner_slip,
        "monthly_test": winner_months,
        "promotion": decision,
        "validation_shortlist_with_test": shortlist,
        "recent_6h_up_moves": recent,
        "november_trades_of_candidate": case_trades,
        "research_rule": research["name"],
        "live_default": "trend" if decision["promote"] else "legacy",
    }
    report["pine"] = pine_source(research if candidate is None else candidate, decision["promote"])
    if spy_dir and spy_dir.exists() and candidate is not None:
        report["spy_mark"] = spy_mark_to_market(spy_dir, winner_trades)
    return report


def spy_mark_to_market(spy_dir: Path, trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    spy = load_ohlc(spy_dir)
    spy_ts = spy.index.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]")
    close = spy["Close"].to_numpy(dtype=float)
    pnls = []
    for trade in trades:
        entry_i = int(np.searchsorted(spy_ts, np.datetime64(trade["entry_ts"].tz_convert("UTC").tz_localize(None))))
        exit_i = int(np.searchsorted(spy_ts, np.datetime64(trade["exit_ts"].tz_convert("UTC").tz_localize(None))))
        if entry_i >= len(close) or exit_i >= len(close):
            continue
        if abs(spy_ts[entry_i] - np.datetime64(trade["entry_ts"].tz_convert("UTC").tz_localize(None))) > np.timedelta64(2, "m"):
            continue
        pnl = trade["side"] * (close[min(exit_i, len(close) - 1)] - close[entry_i]) - 0.02
        pnls.append(pnl)
    if not pnls:
        return {"trades": 0, "note": "No SPY print within 2 minutes of the index entries. Overnight trades have no SPY fill."}
    values = np.array(pnls)
    return {
        "trades": int(len(values)),
        "expectancy_dollars": round(float(values.mean()), 4),
        "win_rate": round(float(np.mean(values > 0)), 4),
        "note": "SPY close-to-close over the same clock times, 1 cent per side. Not a re-optimized SPY stop. Overnight index trades without a SPY bar are omitted.",
    }


def markdown(report: dict) -> str:
    decision = report["promotion"]
    title = "READY" if decision["promote"] else "NOT READY"
    lines = [
        f"# اتجاه 24 ساعة — الحكم: {title}",
        "",
        "لا توجد إشارة اتجاه جاهزة للتداول." if not decision["promote"] else "المرشح اجتاز شرط الاختبار.",
        decision["reason"],
        "",
        f"البيانات من {report['coverage']['first']} إلى {report['coverage']['last']} عند {report['coverage']['last_price']}.",
        report["coverage"]["note"],
        f"عدد الإعدادات: {report['protocol']['configs']}. التكلفة 0.5 نقطة لكل طرف على USA500.",
        f"التقسيم: تدريب {report['split_counts']['train']}، تحقق {report['split_counts']['validation']}، اختبار {report['split_counts']['test']} ({report['split']['test'][0]} إلى {report['split']['test'][-1]}).",
        "",
        "## كم مرة تحدث حركة الاتجاه",
        "",
        "التعريف الأساسي: 0.75% خلال 4 ساعات مع تراجع معاكس قبل الهدف أقل من 0.30%.",
        "",
        "| الهدف | الساعات | عدد الحركات | آسيا | أوروبا | ما قبل نيويورك | جلسة نيويورك | بعد الإغلاق |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["labels"]:
        buckets = row["by_session"]
        lines.append(
            f"| {row['x']*100:.2f}% | {row['hours']} | {row['events']} | {buckets['asia']} | {buckets['europe']} | {buckets['us_pre']} | {buckets['rth']} | {buckets['after']} |"
        )
        if "remaining_after_0.25pct" in row:
            left = row["remaining_after_0.25pct"]
            lines.append("")
            lines.append(
                f"بعد تحرك 0.25% في اتجاه الحركة، الوسيط المتبقي من الامتداد هو {left['median_remaining']} "
                f"(على {left['with_confirmation']} حركة). وسيط الدقائق حتى هذا التأكيد: {left['median_minutes_to_confirm']}."
            )
            lines.append("")
    cand = report["candidate"]
    lines.append("## المرشح المثبت قبل الاختبار")
    lines.append("")
    if cand:
        lines.append(f"`{cand['name']}` فلتر {cand['filter']} خروج {cand['exit']}.")
        lines.append(f"تدريب: توقع {cand['train']['expectancy']} نقطة، عامل ربح {cand['train']['profit_factor']}، صفقات {cand['train']['trades']}.")
        lines.append(f"تحقق: توقع {cand['validation']['expectancy']} نقطة، عامل ربح {cand['validation']['profit_factor']}، صفقات {cand['validation']['trades']}.")
        test = report["test"]
        lines.append(
            f"اختبار: صفقات/يوم {test['trades_per_session']}، فوز {test['win_rate']}، متوسط رابح {test['avg_win']}، "
            f"متوسط خاسر {test['avg_loss']}، توقع {test['expectancy']} ({test['expectancy_ci']})، "
            f"توقع R {test['expectancy_r']}، عامل ربح {test['profit_factor']}، تراجع {test['max_drawdown']}."
        )
        slip = report.get("test_cost_1_point")
        if slip:
            lines.append(f"حساسية نقطة كاملة لكل طرف: توقع {slip['expectancy']} ({slip['expectancy_ci']})، عامل ربح {slip['profit_factor']}.")
        lines.append(f"فحص الواقع: {report['reality_check']}.")
        lines.append(f"شارب المخفّض: {report['deflated_sharpe']}.")
    else:
        lines.append("لا إعداد كان رابحًا على التدريب والتحقق معًا.")
    lines.append("")
    lines.append("| الإعداد | مؤهل | توقع التحقق | توقع الاختبار | الفترة | عامل الربح |")
    lines.append("| --- | --- | ---: | ---: | --- | ---: |")
    for row in report["validation_shortlist_with_test"]:
        test = row["test"]
        lines.append(
            f"| {row['name']} | {row['eligible']} | {row['validation_expectancy']} | {test['expectancy']} | {test['expectancy_ci']} | {test['profit_factor']} |"
        )
    if report.get("monthly_test"):
        lines.append("")
        lines.append("شهور الاختبار:")
        for row in report["monthly_test"]:
            lines.append(f"- {row['month']}: مجموع {row['total']} نقطة على {row['trades']} صفقة")
    lines.append("")
    lines.append("## آخر البيانات وحركة 10/11 نوفمبر")
    lines.append("")
    lines.append("أكبر صعودات 6 ساعات منذ 1 نوفمبر:")
    for row in report["recent_6h_up_moves"]:
        lines.append(f"- {row['start']} من {row['from']} إلى {row['to']} ({row['points']} نقطة) حتى {row['peak']}")
    if report["november_trades_of_candidate"]:
        lines.append("صفقات نوفمبر للمرشح:")
        for row in report["november_trades_of_candidate"]:
            lines.append(f"- {row['entry']} → {row['exit']} اتجاه {row['side']} نتيجة {row['pnl']}")
    else:
        lines.append("لا صفقة للمرشح في نوفمبر داخل الأرشيف.")
    if report.get("spy_mark"):
        lines.append("")
        lines.append(f"ترجمة SPY لنفس أوقات الدخول والخروج: {report['spy_mark']}.")
    lines.append("")
    lines.append(f"سكربت بين هو `{report['research_rule']}` وبعلامة RESEARCH_ONLY ما لم يكن الحكم READY. الإعداد الحي يبقى القاعدة القديمة.")
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="24h trend study")
    parser.add_argument("--usa", default="/tmp/trend_src/h24/spx_24h/USA500")
    parser.add_argument("--tech", default="/tmp/trend_src/h24/spx_24h/USATECH")
    parser.add_argument("--extra", action="append", default=[])
    parser.add_argument("--spy", default="data/archive/dukascopy/spx_history/SPY")
    parser.add_argument("--output", default="artifacts/trend_24h/report.json")
    args = parser.parse_args()
    roots = [Path(path) for path in args.extra] or [
        Path("/tmp/trend_src/mega"),
        Path("/tmp/trend_src/sectors/spx_breadth"),
        Path("/tmp/trend_src/cross/spx_breadth"),
    ]
    report = run(Path(args.usa), Path(args.tech), roots, Path(args.spy))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pine = report.pop("pine")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    destination.with_name("REPORT.md").write_text(markdown(report), encoding="utf-8")
    destination.with_name("trend_research.pine").write_text(pine, encoding="utf-8")
    print(markdown(report))
    print("PROMOTE", report["promotion"]["promote"], report.get("candidate"))


if __name__ == "__main__":
    main()
