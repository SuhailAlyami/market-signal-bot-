"""Confirmation entries and exits on the 466-session Dukascopy sample.

Parameters are frozen before the test split is scored. The grid below is the
whole search: nothing is added after seeing validation or test numbers.

Selection, locked now:
- A config is eligible only if train and validation both have positive
  expectancy per trade, train has at least 40 trades, validation at least 15,
  and validation profit factor is above 1.
- The candidate is the eligible config with the highest validation expectancy.
  Ties break toward higher validation profit factor, then more validation trades.
- White's reality check and the deflated Sharpe ratio use train+validation
  daily PnL across every config. They are not refit on the test set.
- READY requires the candidate's test expectancy interval (1 cent per side)
  to lie above zero, reality-check p < 0.05, deflated Sharpe >= 0.95,
  and test profit factor > 1.2.
- Two-cent slippage is a sensitivity, not a second search.

Entry is the next one-minute open. One position at a time. Stop is known at
the bar open; trail and breakeven tighten only for later bars. If stop and
target are both inside a bar, the stop fills.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from long_explosion_study import _align, prepare
from research_1m_lead import five_minute_atr

TRAIN_END = date(2026, 2, 13)
VAL_END = date(2026, 6, 30)
TEST_START = date(2026, 7, 1)
SLIP = 0.01
EULER = 0.5772156649015329
NORMAL = NormalDist()

# Default exit for the entry search: 1 ATR stop, 2R target, 30-minute time stop.
DEFAULT_EXIT = {"stop": 1.0, "target_r": 2.0, "time": 30, "trail": 0.0, "be": 0}
EXIT_PRESETS = (
    {"stop": 1.0, "target_r": 1.0, "time": 30, "trail": 0.0, "be": 0},
    {"stop": 1.0, "target_r": 3.0, "time": 30, "trail": 0.0, "be": 0},
    {"stop": 1.0, "target_r": 2.0, "time": 10, "trail": 0.0, "be": 0},
    {"stop": 1.0, "target_r": 2.0, "time": 20, "trail": 0.0, "be": 0},
    {"stop": 1.0, "target_r": 2.0, "time": 30, "trail": 1.5, "be": 0},
    {"stop": 1.0, "target_r": 2.0, "time": 30, "trail": 0.0, "be": 1},
    {"stop": 0.75, "target_r": 1.5, "time": 30, "trail": 0.0, "be": 1},
)


def split_dates(sessions: list[date]) -> dict[str, list[date]]:
    return {
        "train": [day for day in sessions if day <= TRAIN_END],
        "validation": [day for day in sessions if TRAIN_END < day <= VAL_END],
        "test": [day for day in sessions if day >= TEST_START],
    }


def rolling_prior(values: np.ndarray, day_id: np.ndarray, window: int, how: str) -> np.ndarray:
    """Max or min of the previous `window` bars inside the same session."""
    out = np.full(len(values), np.nan)
    cuts = np.flatnonzero(day_id[1:] != day_id[:-1]) + 1
    bounds = np.r_[0, cuts, len(values)]
    for start, end in zip(bounds[:-1], bounds[1:]):
        segment = values[start:end]
        if len(segment) <= window:
            continue
        rolled = pd.Series(segment).rolling(window, min_periods=window)
        stats = rolled.max().to_numpy() if how == "max" else rolled.min().to_numpy()
        out[start + 1:end] = stats[:-1]
    return out


def same_day_return(values: np.ndarray, day_id: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if window >= len(values):
        return out
    base = values[:-window]
    with np.errstate(divide="ignore", invalid="ignore"):
        change = np.where(base > 0, values[window:] / base - 1, np.nan)
    change = np.where(day_id[window:] == day_id[:-window], change, np.nan)
    out[window:] = change
    return out


def fresh_cross(close: np.ndarray, level: np.ndarray, day_id: np.ndarray, side: int, bars: int) -> np.ndarray:
    beyond = (side * (close - level) > 0) & np.isfinite(level)
    previous = np.zeros(len(close), dtype=bool)
    if bars < len(close):
        previous[bars:] = beyond[:-bars] & (day_id[bars:] == day_id[:-bars])
    return beyond & ~previous


def _segments(day_id: np.ndarray) -> list[tuple[int, int]]:
    cuts = np.flatnonzero(day_id[1:] != day_id[:-1]) + 1
    bounds = np.r_[0, cuts, len(day_id)]
    return list(zip(bounds[:-1], bounds[1:]))


def opening_range(high: np.ndarray, low: np.ndarray, day_id: np.ndarray, session_minute: np.ndarray, window: int):
    """High/low from minute 0 through window-1. Usable from the first later bar."""
    hi = np.full(len(high), np.nan)
    lo = np.full(len(low), np.nan)
    for start, end in _segments(day_id):
        minutes = session_minute[start:end]
        forming = np.flatnonzero(minutes < window)
        if len(forming) == 0 or not np.any(minutes >= window):
            continue
        locked_high = float(np.max(high[start:end][forming]))
        locked_low = float(np.min(low[start:end][forming]))
        ready = minutes >= window
        hi[start:end][ready] = locked_high
        lo[start:end][ready] = locked_low
    return hi, lo


def simulate(index, day_id, open_, high, low, close, signal_i, signal_side, atr, exit_rule, slip):
    """Next-bar entry, one position, adverse slippage on the entry and the exit."""
    trades = []
    if len(signal_i) == 0:
        return trades
    order = np.argsort(signal_i, kind="mergesort")
    signal_i = signal_i[order]
    signal_side = signal_side[order]
    n = len(close)
    busy_until = -1
    stop_mult = exit_rule["stop"]
    target_r = exit_rule["target_r"]
    time_stop = exit_rule["time"]
    trail = exit_rule["trail"]
    use_be = exit_rule["be"] == 1
    for i, side in zip(signal_i, signal_side):
        i = int(i)
        side = int(side)
        entry_i = i + 1
        if entry_i <= busy_until or entry_i >= n or day_id[entry_i] != day_id[i]:
            continue
        if index[entry_i] - index[i] != np.timedelta64(1, "m"):
            continue
        risk_unit = float(atr[i]) * stop_mult
        if not np.isfinite(risk_unit) or risk_unit <= 0:
            continue
        quote = float(open_[entry_i])
        entry = quote + side * slip
        # Stop and target are measured from the quoted open, so both sides pay the cent.
        stop = quote - side * risk_unit
        target = quote + side * target_r * risk_unit
        exit_price = None
        exit_i = None
        last = None
        for j in range(entry_i, min(n, entry_i + time_stop)):
            if day_id[j] != day_id[entry_i]:
                break
            last = j
            if side > 0:
                hit_stop = low[j] <= stop
                hit_target = high[j] >= target
            else:
                hit_stop = high[j] >= stop
                hit_target = low[j] <= target
            if hit_stop:
                exit_price = stop - side * slip
                exit_i = j
                break
            if hit_target:
                exit_price = target - side * slip
                exit_i = j
                break
            favorable = high[j] if side > 0 else low[j]
            if trail > 0:
                trailed = favorable - side * trail * float(atr[i])
                stop = max(stop, trailed) if side > 0 else min(stop, trailed)
            if use_be and side * (favorable - quote) >= risk_unit:
                stop = max(stop, quote) if side > 0 else min(stop, quote)
        if exit_price is None and last is not None:
            exit_price = float(close[last] - side * slip)
            exit_i = last
        if exit_price is None:
            continue
        pnl = side * (exit_price - entry)
        trades.append((float(pnl), float(pnl / risk_unit), day_id[entry_i], exit_i))
        busy_until = exit_i
    return trades


def _day_blocks(trades, day_lookup):
    grouped: dict = {}
    for pnl, r_mult, day_code, _exit in trades:
        day = day_lookup[int(day_code)]
        grouped.setdefault(day, []).append((pnl, r_mult))
    return grouped


def summarize(trades, sessions, day_lookup, draws=500, seed=16) -> dict:
    n_sessions = len(sessions)
    if not trades:
        return {
            "trades": 0, "trades_per_session": 0.0, "win_rate": None, "avg_win": None,
            "avg_loss": None, "expectancy": None, "expectancy_ci": None, "expectancy_r": None,
            "profit_factor": None, "max_drawdown": None,
        }
    pnls = np.array([item[0] for item in trades], dtype=float)
    rs = np.array([item[1] for item in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    equity = np.cumsum(pnls)
    drawdown = float(np.max(np.maximum.accumulate(equity) - equity))
    grouped = _day_blocks(trades, day_lookup)
    ci = None
    active = [day for day in sessions if day in grouped]
    if len(active) >= 2:
        rng = np.random.default_rng(seed)
        samples = []
        for _ in range(draws):
            chosen = rng.choice(len(sessions), size=len(sessions), replace=True)
            pool = [pnl for k in chosen for pnl, _r in grouped.get(sessions[k], ())]
            if pool:
                samples.append(float(np.mean(pool)))
        if samples:
            ci = [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]
    profit_factor = None
    if losses.size:
        profit_factor = float(wins.sum() / abs(losses.sum())) if wins.size else 0.0
    elif wins.size:
        profit_factor = None
    return {
        "trades": int(len(trades)),
        "trades_per_session": round(len(trades) / n_sessions, 4) if n_sessions else None,
        "win_rate": round(float(np.mean(pnls > 0)), 4),
        "avg_win": round(float(wins.mean()), 4) if wins.size else None,
        "avg_loss": round(float(losses.mean()), 4) if losses.size else None,
        "expectancy": round(float(pnls.mean()), 4),
        "expectancy_ci": ci,
        "expectancy_r": round(float(rs.mean()), 4),
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "max_drawdown": round(drawdown, 4),
    }


def eligible(train: dict, validation: dict) -> bool:
    return bool(
        train["trades"] >= 40
        and validation["trades"] >= 15
        and (train["expectancy"] or 0) > 0
        and (validation["expectancy"] or 0) > 0
        and ((validation["profit_factor"] is None and validation["trades"] > 0) or (validation["profit_factor"] or 0) > 1)
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


def whites_reality_check(daily: np.ndarray, candidate_mean: float, draws=500, seed=23) -> dict:
    """P-value for the candidate mean against the best-of-N null."""
    if daily.size == 0 or not np.isfinite(candidate_mean):
        return {"p_value": 1.0, "hurdle_95": None, "survives": False}
    observed = daily.mean(axis=0)
    centered = daily - observed
    rng = np.random.default_rng(seed)
    hurdles = np.empty(draws)
    n_days = daily.shape[0]
    for draw in range(draws):
        pick = rng.integers(0, n_days, size=n_days)
        hurdles[draw] = centered[pick].mean(axis=0).max()
    p_value = float(np.mean(hurdles >= candidate_mean))
    return {
        "p_value": round(p_value, 4),
        "hurdle_95": round(float(np.quantile(hurdles, 0.95)), 4),
        "candidate_daily_mean": round(float(candidate_mean), 4),
        "survives": bool(p_value < 0.05),
        "draws": draws,
    }


def deflated_sharpe(daily: np.ndarray, n_trials: int) -> dict:
    """Bailey and Lopez de Prado deflated Sharpe on daily PnL. DSR is a probability."""
    sharpes = []
    for col in range(daily.shape[1]):
        series = daily[:, col]
        std = float(series.std(ddof=1))
        sharpes.append(0.0 if std == 0 else float(series.mean() / std))
    sharpes = np.array(sharpes)
    variance = float(sharpes.var(ddof=1)) if len(sharpes) > 1 else 0.0
    if n_trials < 2 or variance <= 0:
        sr_star = 0.0
    else:
        z1 = NORMAL.inv_cdf(1 - 1 / n_trials)
        z2 = NORMAL.inv_cdf(1 - 1 / (n_trials * np.e))
        sr_star = float(np.sqrt(variance) * ((1 - EULER) * z1 + EULER * z2))
    return {"sr_star": sr_star, "trial_sharpes": sharpes}


def deflated_sharpe_of(series: np.ndarray, sr_star: float) -> dict:
    series = np.asarray(series, dtype=float)
    length = len(series)
    std = float(series.std(ddof=1)) if length > 2 else 0.0
    if length < 10 or std == 0:
        return {"sharpe_daily": 0.0, "dsr": 0.0, "survives": False}
    sr = float(series.mean() / std)
    centered = (series - series.mean()) / std
    skew = float(np.mean(centered ** 3))
    kurt = float(np.mean(centered ** 4))
    denom = 1 - skew * sr + ((kurt - 1) / 4) * sr ** 2
    if denom <= 0:
        return {"sharpe_daily": round(sr, 4), "dsr": 0.0, "survives": False}
    z = (sr - sr_star) * np.sqrt(length - 1) / np.sqrt(denom)
    dsr = float(NORMAL.cdf(z))
    return {"sharpe_daily": round(sr, 4), "sr_star": round(sr_star, 4), "dsr": round(dsr, 4), "survives": dsr >= 0.95}


def promotion_decision(candidate, test_metrics, reality, dsr) -> dict:
    if candidate is None or test_metrics is None:
        return {"promote": False, "reason": "no config was positive on both train and validation"}
    ci = test_metrics.get("expectancy_ci") or [None, None]
    pf = test_metrics.get("profit_factor") or 0
    reasons = []
    if not (ci[0] is not None and ci[0] > 0):
        reasons.append("test expectancy interval does not lie above zero")
    if not reality.get("survives"):
        reasons.append("reality check does not clear best-of-N")
    if not dsr.get("survives"):
        reasons.append("deflated Sharpe is below 0.95")
    if not (pf > 1.2):
        reasons.append("profit factor is not above 1.2")
    ok = not reasons
    return {
        "promote": ok,
        "reason": "test expectancy stays positive after the multiple-testing haircut" if ok else "; ".join(reasons),
        "profit_factor": pf,
        "expectancy_ci": ci,
    }


def _apply_filter(bull, bear, name, features, spec) -> tuple[np.ndarray, np.ndarray]:
    if name == "none":
        return bull, bear
    if name == "qqq":
        return bull & features["up"][spec], bear & features["down"][spec]
    if name == "gspc":
        return bull & features["gup"][spec], bear & features["gdown"][spec]
    if name == "qqq_gspc":
        return bull & features["up"][spec] & features["gup"][spec], bear & features["down"][spec] & features["gdown"][spec]
    if name == "no_first_30":
        return bull & features["after_open"], bear & features["after_open"]
    if name == "no_last_30":
        return bull & features["before_close"], bear & features["before_close"]
    if name == "only_first_30":
        return bull & features["first_30"], bear & features["first_30"]
    if name == "only_last_30":
        return bull & features["last_30"], bear & features["last_30"]
    if name == "gap":
        return bull & features["gap_up"], bear & features["gap_down"]
    if name == "pdhl":
        return bull & features["above_pdh"], bear & features["below_pdl"]
    if name == "vwap":
        return bull & features["vwap_up"], bear & features["vwap_down"]
    if name.startswith("orb"):
        window = int(name[3:])
        return bull & features["orb_up"][window], bear & features["orb_down"][window]
    if name == "rv_low":
        return bull & features["rv_low"], bear & features["rv_low"]
    if name == "rv_high":
        return bull & features["rv_high"], bear & features["rv_high"]
    if name == "pdr_low":
        return bull & features["pdr_low"], bear & features["pdr_low"]
    if name == "pdr_high":
        return bull & features["pdr_high"], bear & features["pdr_high"]
    raise KeyError(name)


def _signals_from_masks(bull: np.ndarray, bear: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    both = bull & bear
    bull = bull & ~both
    bear = bear & ~both
    ib = np.flatnonzero(bull)
    ia = np.flatnonzero(bear)
    idx = np.concatenate([ib, ia]) if len(ia) or len(ib) else np.array([], dtype=int)
    side = np.concatenate([np.ones(len(ib), dtype=int), -np.ones(len(ia), dtype=int)]) if len(idx) else np.array([], dtype=int)
    return idx.astype(int), side.astype(int)


def build_features(market: dict) -> dict:
    close = market["close"]
    high = market["high"]
    low = market["low"]
    day_id = market["day_id"]
    dates = market["dates"]
    session_minute = market["minutes"] - (9 * 60 + 30)
    atr = _align(five_minute_atr(market["frame"]), market["index"], limit=20)
    windows = (15, 30, 60)
    prior_high = {n: rolling_prior(high, day_id, n, "max") for n in windows}
    prior_low = {n: rolling_prior(low, day_id, n, "min") for n in windows}
    qqq_ret = {n: same_day_return(market["qqq"], day_id, n) for n in (5, 15, 30, 60)}
    gspc_ret = {n: same_day_return(market["gspc"], day_id, n) for n in (5, 15, 30, 60)}
    or_high = {}
    or_low = {}
    for window in (5, 15, 30):
        or_high[window], or_low[window] = opening_range(high, low, day_id, session_minute, window)
    # Prior-day high, low, close, and the opening gap. Known before the session trades.
    day_high = {}
    day_low = {}
    day_close = {}
    day_open = {}
    for start, end in _segments(day_id):
        key = dates[start]
        day_high[key] = float(np.max(high[start:end]))
        day_low[key] = float(np.min(low[start:end]))
        day_close[key] = float(close[end - 1])
        day_open[key] = float(market["open"][start])
    ordered = sorted(day_high)
    pdh = np.full(len(close), np.nan)
    pdl = np.full(len(close), np.nan)
    gap = np.full(len(close), np.nan)
    pdr_pct = np.full(len(close), np.nan)
    history = []
    for pos, day in enumerate(ordered):
        if pos:
            prev = ordered[pos - 1]
            mask = dates == day
            pdh[mask] = day_high[prev]
            pdl[mask] = day_low[prev]
            if day_close[prev] > 0:
                gap[mask] = day_open[day] / day_close[prev] - 1
            if len(history) >= 20:
                rng = (day_high[prev] - day_low[prev]) / day_close[prev]
                pdr_pct[mask] = float(np.mean(np.asarray(history[-60:]) <= rng))
            history.append((day_high[prev] - day_low[prev]) / day_close[prev])
    # Realized vol percentile versus the same minute on the prior 20 sessions.
    log_ret = np.zeros(len(close))
    log_ret[1:] = np.diff(np.log(np.maximum(close, 1e-9)))
    log_ret[1:] = np.where(day_id[1:] == day_id[:-1], log_ret[1:], 0)
    rv = pd.Series(log_ret).rolling(30, min_periods=30).std().to_numpy()
    rv = np.where(session_minute >= 29, rv, np.nan)
    rv_pct = np.full(len(close), np.nan)
    buckets: dict[int, list[float]] = {}
    pending: dict[int, list[float]] = {}
    current = None
    for i in range(len(close)):
        if dates[i] != current:
            for minute, values in pending.items():
                store = buckets.setdefault(minute, [])
                store.extend(values)
                if len(store) > 20:
                    del store[:-20]
            pending = {}
            current = dates[i]
        minute = int(session_minute[i])
        if np.isfinite(rv[i]) and minute in buckets and buckets[minute]:
            sample = buckets[minute]
            rv_pct[i] = float(np.sum(np.asarray(sample) <= rv[i]) / len(sample))
        if np.isfinite(rv[i]):
            pending.setdefault(minute, []).append(float(rv[i]))
    typical = (high + low + close) / 3
    vwap = np.full(len(close), np.nan)
    for start, end in _segments(day_id):
        vol = market["volume"][start:end]
        price = typical[start:end]
        traded = np.where(vol > 0, vol, 0)
        cum_pv = np.cumsum(price * traded)
        cum_v = np.cumsum(traded)
        with np.errstate(divide="ignore", invalid="ignore"):
            vwap[start:end] = np.where(cum_v > 0, cum_pv / cum_v, np.nan)
    prev_close = np.roll(close, 1)
    prev_vwap = np.roll(vwap, 1)
    same = np.zeros(len(close), dtype=bool)
    same[1:] = day_id[1:] == day_id[:-1]
    vwap_up = same & np.isfinite(vwap) & (close > vwap) & (prev_close <= prev_vwap) & (session_minute >= 15)
    vwap_down = same & np.isfinite(vwap) & (close < vwap) & (prev_close >= prev_vwap) & (session_minute >= 15)
    up = {n: qqq_ret[n] > 0 for n in qqq_ret}
    down = {n: qqq_ret[n] < 0 for n in qqq_ret}
    gup = {n: gspc_ret[n] > 0 for n in gspc_ret}
    gdown = {n: gspc_ret[n] < 0 for n in gspc_ret}
    orb_up = {}
    orb_down = {}
    for window in (5, 15, 30):
        orb_up[window] = np.isfinite(or_high[window]) & (close > or_high[window])
        orb_down[window] = np.isfinite(or_low[window]) & (close < or_low[window])
        up[window] = up.get(window, qqq_ret[window] > 0)
        down[window] = down.get(window, qqq_ret[window] < 0)
        gup[window] = gup.get(window, gspc_ret[window] > 0)
        gdown[window] = gdown.get(window, gspc_ret[window] < 0)
    return {
        "atr": atr, "prior_high": prior_high, "prior_low": prior_low, "or_high": or_high, "or_low": or_low,
        "pdh": pdh, "pdl": pdl, "gap": gap, "session_minute": session_minute,
        "up": up, "down": down, "gup": gup, "gdown": gdown, "orb_up": orb_up, "orb_down": orb_down,
        "after_open": session_minute >= 30, "before_close": session_minute < 360,
        "first_30": (session_minute >= 0) & (session_minute < 30), "last_30": session_minute >= 360,
        "gap_up": gap >= 0.001, "gap_down": gap <= -0.001,
        "above_pdh": np.isfinite(pdh) & (close > pdh), "below_pdl": np.isfinite(pdl) & (close < pdl),
        "vwap_up": vwap_up, "vwap_down": vwap_down,
        "rv_low": rv_pct < 0.33, "rv_high": rv_pct > 0.66,
        "pdr_low": pdr_pct < 0.33, "pdr_high": pdr_pct > 0.66,
        "vwap": vwap,
    }


def build_configs() -> list[dict]:
    """The entire predeclared search. Do not append to this after a run."""
    configs = []
    for n in (15, 30, 60):
        for k in (0.25, 0.5, 1.0):
            for bars in (1, 5):
                configs.append({
                    "name": f"break_n{n}_k{k}_m{bars}", "kind": "break",
                    "n": n, "k": k, "m": bars, "filter": "none", "exit": dict(DEFAULT_EXIT),
                })
    for filt in (
        "qqq", "gspc", "qqq_gspc", "no_first_30", "no_last_30", "only_first_30", "only_last_30",
        "orb5", "orb15", "orb30", "pdhl", "vwap", "gap",
    ):
        configs.append({
            "name": f"break_n30_k0.5_m1_{filt}", "kind": "break",
            "n": 30, "k": 0.5, "m": 1, "filter": filt, "exit": dict(DEFAULT_EXIT),
        })
    for n in (15, 30, 60):
        for k in (0.5, 1.0):
            for filt in ("none", "no_first_30"):
                configs.append({
                    "name": f"fade_n{n}_k{k}_{filt}", "kind": "fade",
                    "n": n, "k": k, "m": 1, "filter": filt, "exit": dict(DEFAULT_EXIT),
                })
    for window in (5, 15, 30):
        for k in (0.0, 0.25):
            for filt in ("none", "qqq_gspc", "no_last_30"):
                configs.append({
                    "name": f"orb{window}_k{k}_{filt}", "kind": "orb",
                    "n": window, "k": k, "m": 1, "filter": filt, "exit": dict(DEFAULT_EXIT),
                })
    for k in (0.0, 0.25):
        for filt in ("none", "gap"):
            configs.append({
                "name": f"pdhl_k{k}_{filt}", "kind": "pdhl",
                "n": 30, "k": k, "m": 1, "filter": filt, "exit": dict(DEFAULT_EXIT),
            })
    for filt in ("none", "qqq_gspc"):
        configs.append({
            "name": f"vwap_cross_{filt}", "kind": "vwap",
            "n": 15, "k": 0.0, "m": 1, "filter": filt, "exit": dict(DEFAULT_EXIT),
        })
    for kind, spec in (
        ("break", {"n": 30, "k": 0.5, "m": 1}),
        ("orb", {"n": 15, "k": 0.0, "m": 1}),
        ("fade", {"n": 30, "k": 0.5, "m": 1}),
    ):
        for filt in ("rv_low", "rv_high", "pdr_low", "pdr_high"):
            label = "orb15" if kind == "orb" else f"{kind}_n30_k0.5"
            configs.append({
                "name": f"{label}_{filt}", "kind": kind, "filter": filt, "exit": dict(DEFAULT_EXIT),
                **spec,
            })
    for anchor in (
        {"kind": "break", "n": 30, "k": 0.5, "m": 1, "filter": "none", "tag": "break_n30_k0.5_m1"},
        {"kind": "orb", "n": 15, "k": 0.0, "m": 1, "filter": "none", "tag": "orb15_k0.0_none"},
        {"kind": "fade", "n": 30, "k": 0.5, "m": 1, "filter": "none", "tag": "fade_n30_k0.5_none"},
    ):
        for preset in EXIT_PRESETS:
            configs.append({
                "name": f"{anchor['tag']}_s{preset['stop']}_t{preset['target_r']}_h{preset['time']}_tr{preset['trail']}_be{preset['be']}",
                "kind": anchor["kind"], "n": anchor["n"], "k": anchor["k"], "m": anchor["m"],
                "filter": "none", "exit": dict(preset),
            })
    names = [cfg["name"] for cfg in configs]
    if len(names) != len(set(names)):
        raise RuntimeError("config names must be unique")
    return configs


def _offset_level(base: np.ndarray, atr: np.ndarray, k: float, side: int) -> np.ndarray:
    if k == 0:
        return base
    return base + side * k * atr


def signals_for(cfg: dict, market: dict, features: dict) -> tuple[np.ndarray, np.ndarray]:
    close = market["close"]
    day_id = market["day_id"]
    atr = features["atr"]
    n = cfg["n"]
    k = cfg["k"]
    if cfg["kind"] == "break":
        up_level = _offset_level(features["prior_high"][n], atr, k, 1)
        dn_level = _offset_level(features["prior_low"][n], atr, k, -1)
        bull = fresh_cross(close, up_level, day_id, 1, cfg["m"])
        bear = fresh_cross(close, dn_level, day_id, -1, cfg["m"])
        bull, bear = _apply_filter(bull, bear, cfg["filter"], features, n)
        return _signals_from_masks(bull, bear)
    if cfg["kind"] == "fade":
        up_level = _offset_level(features["prior_high"][n], atr, k, 1)
        dn_level = _offset_level(features["prior_low"][n], atr, k, -1)
        bull = fresh_cross(close, up_level, day_id, 1, 1)
        bear = fresh_cross(close, dn_level, day_id, -1, 1)
        failed_i = []
        failed_side = []
        for i in np.flatnonzero(bull):
            level = features["prior_high"][n][i]
            for j in range(i + 1, min(len(close), i + 6)):
                if day_id[j] != day_id[i]:
                    break
                if close[j] < level:
                    failed_i.append(j)
                    failed_side.append(-1)
                    break
        for i in np.flatnonzero(bear):
            level = features["prior_low"][n][i]
            for j in range(i + 1, min(len(close), i + 6)):
                if day_id[j] != day_id[i]:
                    break
                if close[j] > level:
                    failed_i.append(j)
                    failed_side.append(1)
                    break
        if not failed_i:
            return np.array([], dtype=int), np.array([], dtype=int)
        idx = np.asarray(failed_i, dtype=int)
        side = np.asarray(failed_side, dtype=int)
        bull = np.zeros(len(close), dtype=bool)
        bear = np.zeros(len(close), dtype=bool)
        bull[idx[side == 1]] = True
        bear[idx[side == -1]] = True
        bull, bear = _apply_filter(bull, bear, cfg["filter"], features, n)
        return _signals_from_masks(bull, bear)
    if cfg["kind"] == "orb":
        window = cfg["n"]
        bull = fresh_cross(close, _offset_level(features["or_high"][window], atr, k, 1), day_id, 1, 1)
        bear = fresh_cross(close, _offset_level(features["or_low"][window], atr, k, -1), day_id, -1, 1)
        bull, bear = _apply_filter(bull, bear, cfg["filter"], features, window)
        return _signals_from_masks(bull, bear)
    if cfg["kind"] == "pdhl":
        bull = fresh_cross(close, _offset_level(features["pdh"], atr, k, 1), day_id, 1, 1)
        bear = fresh_cross(close, _offset_level(features["pdl"], atr, k, -1), day_id, -1, 1)
        bull, bear = _apply_filter(bull, bear, cfg["filter"], features, 30)
        return _signals_from_masks(bull, bear)
    if cfg["kind"] == "vwap":
        bull = features["vwap_up"].copy()
        bear = features["vwap_down"].copy()
        bull, bear = _apply_filter(bull, bear, cfg["filter"], features, cfg["n"])
        return _signals_from_masks(bull, bear)
    raise KeyError(cfg["kind"])


def monthly_table(trades, day_lookup) -> list[dict]:
    buckets: dict[str, list[float]] = {}
    for pnl, _r, day_code, _exit in trades:
        day = day_lookup[int(day_code)]
        buckets.setdefault(day.strftime("%Y-%m"), []).append(pnl)
    rows = []
    for month in sorted(buckets):
        values = np.array(buckets[month])
        rows.append({
            "month": month, "trades": int(len(values)),
            "expectancy": round(float(values.mean()), 4),
            "total": round(float(values.sum()), 4),
            "win_rate": round(float(np.mean(values > 0)), 4),
        })
    return rows


def run(root: Path) -> dict:
    market = prepare(root)
    print(f"bars {len(market['close'])}", flush=True)
    features = build_features(market)
    configs = build_configs()
    print(f"configs {len(configs)}", flush=True)
    sessions = sorted(set(market["dates"]))
    parts = split_dates(sessions)
    day_lookup = {code: day for code, day in enumerate(pd.unique(market["dates"]))}
    # factorize order matches day_id because prepare uses factorize(sort=False) on chronological dates.
    day_lookup = {i: day for i, day in enumerate(pd.unique(market["dates"]))}
    sets = {name: set(days) for name, days in parts.items()}
    index = market["index"].tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]")
    selection_days = parts["train"] + parts["validation"]
    daily = np.zeros((len(selection_days), len(configs)))
    sel_pos = {day: i for i, day in enumerate(selection_days)}
    rows = []
    cached = []
    for number, cfg in enumerate(configs):
        sig_i, sig_side = signals_for(cfg, market, features)
        trades = simulate(
            index, market["day_id"], market["open"], market["high"], market["low"], market["close"],
            sig_i, sig_side, features["atr"], cfg["exit"], SLIP,
        )
        cached.append(trades)
        grouped = {"train": [], "validation": [], "test": []}
        for trade in trades:
            day = day_lookup[trade[2]]
            for part, days in sets.items():
                if day in days:
                    grouped[part].append(trade)
                    break
            pos = sel_pos.get(day)
            if pos is not None:
                daily[pos, number] += trade[0]
        train_m = summarize(grouped["train"], parts["train"], day_lookup)
        val_m = summarize(grouped["validation"], parts["validation"], day_lookup)
        row = {
            "name": cfg["name"], "kind": cfg["kind"], "params": {k: cfg[k] for k in ("n", "k", "m", "filter")},
            "exit": cfg["exit"], "eligible": eligible(train_m, val_m),
            "train": train_m, "validation": val_m,
        }
        rows.append(row)
        if number % 20 == 0:
            print(f"scored {number + 1}/{len(configs)} {cfg['name']}", flush=True)
    candidate = choose_candidate(rows)
    reality = {"p_value": 1.0, "survives": False}
    dsr = {"dsr": 0.0, "survives": False}
    if candidate is not None:
        col = next(i for i, row in enumerate(rows) if row["name"] == candidate["name"])
        reality = whites_reality_check(daily, float(daily[:, col].mean()))
        sr_star = deflated_sharpe(daily, len(configs))["sr_star"]
        dsr = deflated_sharpe_of(daily[:, col], sr_star)
    # Test is scored once, after the candidate name is fixed.
    test_rows = []
    winner_test = None
    winner_month = None
    winner_slip2 = None
    spx_points = None
    for number, (cfg, trades) in enumerate(zip(configs, cached)):
        test_trades = [trade for trade in trades if day_lookup[trade[2]] in sets["test"]]
        metrics = summarize(test_trades, parts["test"], day_lookup)
        test_rows.append({"name": cfg["name"], "test": metrics})
        if candidate is not None and cfg["name"] == candidate["name"]:
            winner_test = metrics
            winner_month = monthly_table(test_trades, day_lookup)
            slip_trades = simulate(
                index, market["day_id"], market["open"], market["high"], market["low"], market["close"],
                *signals_for(cfg, market, features), features["atr"], cfg["exit"], 0.02,
            )
            slip_test = [trade for trade in slip_trades if day_lookup[trade[2]] in sets["test"]]
            winner_slip2 = summarize(slip_test, parts["test"], day_lookup)
            ratios = []
            close = market["close"]
            gspc = market["gspc"]
            for _pnl, _r, day_code, _exit in test_trades:
                pass
            # Ratio at each test entry, recovered from the cached trade's day only as a session median.
            day_ratio = {}
            for i in range(len(close)):
                if market["dates"][i] in sets["test"] and np.isfinite(gspc[i]) and close[i] > 0:
                    day_ratio.setdefault(market["dates"][i], gspc[i] / close[i])
            if day_ratio and metrics["expectancy"] is not None:
                ratio = float(np.median(list(day_ratio.values())))
                spx_points = {
                    "median_gspc_over_spy": round(ratio, 4),
                    "expectancy_spx_points": round(metrics["expectancy"] * ratio, 4),
                    "note": "SPY dollars times the Dukascopy US500/SPY ratio. SPY is not the index divided by 10.",
                }
    decision = promotion_decision(candidate, winner_test, reality, dsr)
    ranked = sorted(rows, key=lambda row: (row["validation"]["expectancy"] or -999), reverse=True)
    test_by_name = {row["name"]: row["test"] for row in test_rows}
    shortlist = []
    for row in ranked[:12]:
        shortlist.append({
            "name": row["name"], "eligible": row["eligible"],
            "validation_expectancy": row["validation"]["expectancy"],
            "validation_pf": row["validation"]["profit_factor"],
            "train_expectancy": row["train"]["expectancy"],
            "test": test_by_name[row["name"]],
        })
    positive_val = sum(1 for row in rows if (row["validation"]["expectancy"] or 0) > 0)
    return {
        "protocol": {
            "entry": "next 1-minute open",
            "slippage_per_side": SLIP,
            "position": "one at a time; stop checked before trail, breakeven, and target",
            "configs": len(configs),
            "selection": "max validation expectancy among configs with positive train and validation expectancy, validation PF>1, train trades>=40, validation trades>=15",
            "multiple_testing": "White reality check p<0.05 and deflated Sharpe >= 0.95 on train+validation daily PnL",
            "promotion": "test expectancy CI lower > 0 at 1 cent per side, reality check survives, DSR>=0.95, profit factor > 1.2",
            "positive_validation_configs": positive_val,
        },
        "split": {name: [day.isoformat() for day in days] for name, days in parts.items()},
        "split_counts": {name: len(days) for name, days in parts.items()},
        "candidate": None if candidate is None else {
            "name": candidate["name"], "kind": candidate["kind"], "params": candidate["params"],
            "exit": candidate["exit"], "train": candidate["train"], "validation": candidate["validation"],
        },
        "reality_check": reality,
        "deflated_sharpe": {k: v for k, v in dsr.items()},
        "test": winner_test,
        "test_slippage_2c": winner_slip2,
        "monthly_test": winner_month,
        "spx_equivalent": spx_points,
        "promotion": decision,
        "validation_shortlist_with_test": shortlist,
        "live_default": "confirm" if decision["promote"] else "legacy",
    }


def markdown(report: dict) -> str:
    decision = report["promotion"]
    title = "READY" if decision["promote"] else "NOT READY"
    lines = [
        f"# تأكيد الدخول والخروج — الحكم: {title}",
        "",
        decision["reason"],
        "",
        f"عدد الإعدادات المجربة: {report['protocol']['configs']}. الاختيار على التحقق فقط، والاختبار من {report['split']['test'][0]} إلى {report['split']['test'][-1]}.",
        "الدخول على افتتاح الدقيقة التالية. سنت لكل طرف. صفقة واحدة في كل وقت.",
        "",
    ]
    cand = report["candidate"]
    if cand:
        lines.append(f"المرشح المثبت قبل الاختبار: `{cand['name']}` خروج {cand['exit']}.")
        lines.append(f"تدريب: توقع {cand['train']['expectancy']}$، عامل ربح {cand['train']['profit_factor']}، صفقات {cand['train']['trades']}.")
        lines.append(f"تحقق: توقع {cand['validation']['expectancy']}$، عامل ربح {cand['validation']['profit_factor']}، صفقات {cand['validation']['trades']}.")
        test = report["test"]
        lines.append(
            f"اختبار 1 سنت: صفقات/جلسة {test['trades_per_session']}، فوز {test['win_rate']}، "
            f"متوسط رابح {test['avg_win']}، متوسط خاسر {test['avg_loss']}، توقع {test['expectancy']}$ "
            f"({test['expectancy_ci']})، توقع R {test['expectancy_r']}، عامل ربح {test['profit_factor']}، "
            f"أقصى تراجع {test['max_drawdown']}$."
        )
        slip = report["test_slippage_2c"]
        if slip:
            lines.append(f"حساسية 2 سنت: توقع {slip['expectancy']}$ ({slip['expectancy_ci']})، عامل ربح {slip['profit_factor']}.")
        if report["spx_equivalent"]:
            eq = report["spx_equivalent"]
            lines.append(f"ما يعادل SPX تقريبيًا: {eq['expectancy_spx_points']} نقطة (نسبة المؤشر/SPY {eq['median_gspc_over_spy']}).")
        lines.append(f"فحص الواقع: p={report['reality_check'].get('p_value')}، عتبة 95% {report['reality_check'].get('hurdle_95')}.")
        lines.append(f"شارب المخفّض: {report['deflated_sharpe']}.")
    else:
        lines.append("لا إعداد كان رابحًا على التدريب والتحقق معًا.")
    lines.append("")
    lines.append("أعلى إعدادات التحقق، وأرقام اختبارها للعرض فقط. لا يُرقّى إلا المرشح المثبت.")
    lines.append("")
    lines.append("| الإعداد | مؤهل | توقع التحقق | توقع الاختبار | فترة الاختبار | عامل الربح |")
    lines.append("| --- | --- | ---: | ---: | --- | ---: |")
    for row in report["validation_shortlist_with_test"]:
        test = row["test"]
        lines.append(
            f"| {row['name']} | {row['eligible']} | {row['validation_expectancy']} | {test['expectancy']} | {test['expectancy_ci']} | {test['profit_factor']} |"
        )
    if report["monthly_test"]:
        lines.append("")
        lines.append("شهور الاختبار للمرشح:")
        for row in report["monthly_test"]:
            lines.append(f"- {row['month']}: توقع {row['expectancy']}$ على {row['trades']} صفقة، مجموع {row['total']}$")
    lines.append("")
    lines.append("الإعداد الحي يبقى القاعدة القديمة ما لم يكن الحكم READY.")
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Confirmation entry and exit study")
    parser.add_argument("--root", default="data/archive/dukascopy/spx_history")
    parser.add_argument("--output", default="artifacts/explosion_confirm/report.json")
    args = parser.parse_args()
    report = run(Path(args.root))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    destination.with_name("REPORT.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    print("PROMOTE", report["promotion"]["promote"])


if __name__ == "__main__":
    main()
