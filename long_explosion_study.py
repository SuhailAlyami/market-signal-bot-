"""One-shot study on the 22-month Dukascopy 1-minute sample.

Split is chronological and fixed: first 60% train, next 20% validation,
last 20% test. The test split is scored once, after every threshold is frozen.
Dukascopy volume is CFD volume, so every volume rule is paired with a
price-only variant. The VIX series is a CFD, not CBOE VIX.

Promotion requires the test pre-onset catch-rate interval to lie entirely
above the legacy interval and the trade expectancy interval to lie above zero.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_1m_lead import build_events, five_minute_atr, legacy_signals

SLIPPAGE = 0.01
HORIZON = 30


def split_60_20_20(sessions: list) -> dict[str, list]:
    if len(sessions) < 15:
        raise ValueError(f"need at least 15 sessions, found {len(sessions)}")
    n_test = len(sessions) // 5
    n_val = len(sessions) // 5
    return {
        "train": sessions[: len(sessions) - n_val - n_test],
        "validation": sessions[len(sessions) - n_val - n_test: len(sessions) - n_test],
        "test": sessions[-n_test:],
    }


def load_symbol(root: Path, folder: str) -> pd.DataFrame:
    files = sorted((root / folder).glob("*.csv.gz"))
    if not files:
        return pd.DataFrame()
    parts = [
        pd.read_csv(path, usecols=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        for path in files
    ]
    frame = pd.concat(parts, ignore_index=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    for col in ("Open", "High", "Low", "Close", "Volume"):
        frame[col] = frame[col].astype(float)
    return frame


def _align(source: pd.Series, index: pd.DatetimeIndex, limit: int) -> np.ndarray:
    if source.empty:
        return np.full(len(index), np.nan)
    aligned = source.reindex(index.union(source.index)).sort_index().ffill(limit=limit).reindex(index)
    return aligned.to_numpy(dtype=float)


def prepare(root: Path) -> dict:
    spy = load_symbol(root, "SPY")
    qqq = load_symbol(root, "QQQ")
    gspc = load_symbol(root, "GSPC")
    vix = load_symbol(root, "VIX")
    local = spy.index.tz_convert("America/New_York")
    dates = np.array(local.date)
    minutes = np.array(local.hour * 60 + local.minute)
    close = spy["Close"].to_numpy(dtype=float)
    open_ = spy["Open"].to_numpy(dtype=float)
    high = spy["High"].to_numpy(dtype=float)
    low = spy["Low"].to_numpy(dtype=float)
    volume = spy["Volume"].to_numpy(dtype=float)
    day_id, _ = pd.factorize(dates, sort=False)
    return {
        "frame": spy, "index": spy.index, "dates": dates, "day_id": day_id.astype(int),
        "minutes": minutes, "open": open_, "high": high, "low": low, "close": close, "volume": volume,
        "qqq": _align(qqq["Close"], spy.index, 2) if not qqq.empty else np.full(len(spy), np.nan),
        "gspc": _align(gspc["Close"], spy.index, 2) if not gspc.empty else np.full(len(spy), np.nan),
        "vix": _align(vix["Close"], spy.index, 5) if not vix.empty else np.full(len(spy), np.nan),
    }


def _cooldown(indices: np.ndarray, days: np.ndarray, gap: int = 10) -> np.ndarray:
    keep = []
    last_i = -10**9
    last_day = None
    for i in indices:
        if days[i] != last_day or i - last_i >= gap:
            keep.append(int(i))
            last_i = int(i)
            last_day = days[i]
    return np.asarray(keep, dtype=int)


def _events_index(market: dict, events: list[dict]) -> list[dict]:
    index = market["index"]
    located = []
    for event in events:
        onset = int(index.searchsorted(event["onset"]))
        touch = int(index.searchsorted(event["touch"]))
        located.append({**event, "onset_i": onset, "touch_i": touch, "side": 1 if event["direction"] == "BULLISH" else -1})
    return located


def _map_legacy(market: dict, signals: list[dict]) -> list[tuple[int, int]]:
    index = market["index"]
    out = []
    for signal in signals:
        pos = int(index.searchsorted(signal["bar_end"])) - 1
        if pos < 0 or pos >= len(index):
            continue
        if index[pos] + pd.Timedelta(minutes=1) != signal["bar_end"]:
            continue
        out.append((pos, 1 if signal["direction"] == "BULLISH" else -1))
    return out


def rule_signals(market: dict, atr: np.ndarray) -> dict[str, list[tuple[int, int]]]:
    """Fixed pre-onset rules. No parameter search."""
    close = market["close"]
    open_ = market["open"]
    high = market["high"]
    low = market["low"]
    volume = market["volume"]
    minutes = market["minutes"]
    dates = market["dates"]
    n = len(close)
    session_minute = minutes - (9 * 60 + 30)
    ret1 = np.full(n, np.nan)
    ret1[1:] = close[1:] / close[:-1] - 1
    ret5 = np.full(n, np.nan)
    ret5[5:] = close[5:] / close[:-5] - 1
    found: dict[str, list[tuple[int, int]]] = {}

    # Opening drive at the completed 5th, 10th and 15th minute.
    seen = set()
    rows = []
    day_open = {}
    for i in range(n):
        if dates[i] not in day_open:
            day_open[dates[i]] = open_[i]
        if session_minute[i] not in (4, 9, 14) or not np.isfinite(ret1[i]):
            continue
        move = close[i] / day_open[dates[i]] - 1
        side = 0
        if 0.0006 <= move <= 0.0014 and ret1[i] >= 0.0002:
            side = 1
        elif -0.0014 <= move <= -0.0006 and ret1[i] <= -0.0002:
            side = -1
        if side and (dates[i], side) not in seen:
            seen.add((dates[i], side))
            rows.append((i, side))
    found["open_drive"] = rows

    # VWAP deviation starting to widen, still under 0.12%.
    typical = (high + low + close) / 3
    vwap = np.full(n, np.nan)
    pv = vv = 0.0
    current = None
    for i in range(n):
        if dates[i] != current:
            current = dates[i]
            pv = vv = 0.0
        if volume[i] > 0 and np.isfinite(typical[i]):
            pv += typical[i] * volume[i]
            vv += volume[i]
        if vv > 0:
            vwap[i] = pv / vv
    dev = (close - vwap) / close
    vwap_idx = []
    for side, sign in ((1, 1), (-1, -1)):
        mask = (
            (session_minute >= 10) & np.isfinite(dev) & np.isfinite(np.roll(dev, 3))
            & (np.arange(n) >= 3) & (sign * dev >= 0.0004) & (sign * dev <= 0.0012)
            & (sign * (dev - np.roll(dev, 3)) >= 0.0003)
        )
        mask[:3] = False
        # roll can cross the day; drop those.
        same = np.empty(n, dtype=bool)
        same[:3] = False
        same[3:] = dates[3:] == dates[:-3]
        chosen = _cooldown(np.flatnonzero(mask & same), dates, 10)
        vwap_idx.extend((int(i), side) for i in chosen)
    found["vwap_start"] = vwap_idx

    # Weak VIX-CFD move, lagged so the print is already old.
    vix = market["vix"]
    vix_rows = []
    if np.isfinite(vix).sum() > 1000:
        chg = np.full(n, np.nan)
        ok = np.isfinite(vix) & np.isfinite(np.roll(vix, 5)) & (np.roll(vix, 5) != 0)
        chg[ok] = vix[ok] / np.roll(vix, 5)[ok] - 1
        lagged = np.roll(chg, 15)
        lagged[:15] = np.nan
        recent = ret5
        for side, sign in ((-1, 1), (1, -1)):
            # VIX up leads a bearish SPY try, and the index has not already moved 0.10%.
            mask = np.isfinite(lagged) & np.isfinite(recent) & (sign * lagged >= 0.005) & (sign * recent > -0.001)
            if side == 1:
                mask = np.isfinite(lagged) & np.isfinite(recent) & (lagged <= -0.005) & (recent < 0.001)
            chosen = _cooldown(np.flatnonzero(mask), dates, 15)
            vix_rows.extend((int(i), side) for i in chosen)
    found["vix_cfd_lag"] = vix_rows

    # Price-only compression release: tight 6-bar range, then a small close break.
    range_ = high - low
    roll6 = pd.Series(range_).rolling(6, min_periods=6).mean().to_numpy()
    roll30 = pd.Series(range_).rolling(30, min_periods=30).mean().to_numpy()
    prior_high6 = pd.Series(high).rolling(6, min_periods=6).max().shift(1).to_numpy()
    prior_low6 = pd.Series(low).rolling(6, min_periods=6).min().shift(1).to_numpy()
    tight = np.isfinite(roll6) & np.isfinite(roll30) & (roll30 > 0) & (roll6 <= 0.55 * roll30)
    comp = []
    for side, level, sign in ((1, prior_high6, 1), (-1, prior_low6, -1)):
        ext = sign * (close - level) / atr
        mask = tight & np.isfinite(ext) & (ext >= 0.05) & (ext <= 0.45) & (sign * (close - open_) > 0)
        same = np.empty(n, dtype=bool)
        same[:6] = False
        same[6:] = dates[6:] == dates[:-6]
        chosen = _cooldown(np.flatnonzero(mask & same), dates, 10)
        comp.extend((int(i), side) for i in chosen)
    found["compression_release"] = comp

    # First wide bar while the 5-minute return is still small.
    med20 = pd.Series(range_).rolling(20, min_periods=20).median().shift(1).to_numpy()
    wide = np.isfinite(med20) & (med20 > 0) & (range_ >= 2.0 * med20) & np.isfinite(ret5) & (np.abs(ret5) <= 0.0015)
    exp = []
    for side, sign in ((1, 1), (-1, -1)):
        mask = wide & (sign * (close - open_) > 0) & (sign * ret1 > 0)
        chosen = _cooldown(np.flatnonzero(mask), dates, 10)
        exp.extend((int(i), side) for i in chosen)
    found["range_expansion"] = exp

    # QQQ moved first; SPY has only started to follow.
    qqq = market["qqq"]
    qret = np.full(n, np.nan)
    qret[5:] = qqq[5:] / qqq[:-5] - 1
    qlag = np.roll(qret, 1)
    qlag[0] = np.nan
    lead = []
    for side, sign in ((1, 1), (-1, -1)):
        mask = (
            np.isfinite(qlag) & np.isfinite(ret5)
            & (sign * qlag >= 0.0008) & (sign * ret5 >= 0) & (sign * ret5 <= 0.0006)
        )
        chosen = _cooldown(np.flatnonzero(mask), dates, 10)
        lead.extend((int(i), side) for i in chosen)
    found["qqq_lead"] = lead

    gspc = market["gspc"]
    gret = np.full(n, np.nan)
    gret[5:] = gspc[5:] / gspc[:-5] - 1
    glag = np.roll(gret, 1)
    glag[0] = np.nan
    div = []
    for side, sign in ((1, 1), (-1, -1)):
        mask = (
            np.isfinite(glag) & np.isfinite(ret5)
            & (sign * glag >= 0.0008) & (sign * ret5 >= 0) & (sign * ret5 <= 0.0006)
        )
        chosen = _cooldown(np.flatnonzero(mask), dates, 10)
        div.extend((int(i), side) for i in chosen)
    found["gspc_lead"] = div

    # Opening-range break after minute 30, while the extension is still under 0.10%.
    or_high = np.full(n, np.nan)
    or_low = np.full(n, np.nan)
    running_h = running_l = np.nan
    count = 0
    current = None
    locked_h = locked_l = np.nan
    for i in range(n):
        if dates[i] != current:
            current = dates[i]
            running_h = running_l = np.nan
            count = 0
            locked_h = locked_l = np.nan
        running_h = high[i] if not np.isfinite(running_h) else max(running_h, high[i])
        running_l = low[i] if not np.isfinite(running_l) else min(running_l, low[i])
        count += 1
        if count == 30:
            locked_h, locked_l = running_h, running_l
        if count > 30:
            or_high[i] = locked_h
            or_low[i] = locked_l
    orb = []
    seen = set()
    for i in range(n):
        if not np.isfinite(or_high[i]) or close[i] <= 0:
            continue
        side = 0
        if close[i] > or_high[i] and (close[i] - or_high[i]) / close[i] <= 0.001:
            side = 1
        elif close[i] < or_low[i] and (or_low[i] - close[i]) / close[i] <= 0.001:
            side = -1
        if side and (dates[i], side) not in seen:
            seen.add((dates[i], side))
            orb.append((i, side))
    found["opening_range"] = orb
    return found


def _labels(n: int, events: list[dict], day_id: np.ndarray) -> np.ndarray:
    label = np.zeros(n, dtype=int)
    for event in reversed(events):
        onset = event["onset_i"]
        side = event["side"]
        lo = onset - 1
        while lo >= 0 and onset - lo <= 30 and day_id[lo] == day_id[onset]:
            label[lo] = side
            lo -= 1
    return label


def _features(market: dict, atr: np.ndarray) -> np.ndarray:
    close = market["close"]
    high = market["high"]
    low = market["low"]
    minutes = market["minutes"]
    n = len(close)
    ret1 = np.zeros(n)
    ret5 = np.zeros(n)
    ret15 = np.zeros(n)
    ret1[1:] = close[1:] / close[:-1] - 1
    ret5[5:] = close[5:] / close[:-5] - 1
    ret15[15:] = close[15:] / close[:-15] - 1
    day_open = np.empty(n)
    current = None
    opener = close[0]
    for i in range(n):
        if market["dates"][i] != current:
            current = market["dates"][i]
            opener = market["open"][i]
        day_open[i] = opener
    dist_open = close / day_open - 1
    range_ = high - low
    roll6 = pd.Series(range_).rolling(6, min_periods=6).mean().to_numpy()
    roll30 = pd.Series(range_).rolling(30, min_periods=30).mean().to_numpy()
    ratio = np.divide(roll6, roll30, out=np.zeros(n), where=roll30 > 0)
    qqq = market["qqq"]
    gspc = market["gspc"]
    qret = np.zeros(n)
    gret = np.zeros(n)
    with np.errstate(divide="ignore", invalid="ignore"):
        qret[5:] = np.where(qqq[:-5] > 0, qqq[5:] / qqq[:-5] - 1, 0)
        gret[5:] = np.where(gspc[:-5] > 0, gspc[5:] / gspc[:-5] - 1, 0)
    qlag = np.roll(qret, 1)
    glag = np.roll(gret, 1)
    qlag[0] = glag[0] = 0
    vix = market["vix"]
    base = np.roll(vix, 15)
    vchg = np.zeros(n)
    known = (base > 0) & np.isfinite(vix) & np.isfinite(base)
    vchg[known] = vix[known] / base[known] - 1
    vchg[:15] = 0
    minute_frac = (minutes - 9 * 60 - 30) / 390
    cols = np.column_stack([
        ret1, ret5, ret15, dist_open, ratio, qlag - ret5, glag - ret5, vchg, minute_frac,
        np.divide(range_, atr, out=np.zeros(n), where=atr > 0),
    ])
    return np.nan_to_num(cols, nan=0.0, posinf=0.0, neginf=0.0)


def _fit_logit(x_train: np.ndarray, y_train: np.ndarray, l2: float = 2.0) -> np.ndarray:
    """Binary L2 logistic regression. Returns weights including intercept."""
    pos = max(1, int(y_train.sum()))
    weight = np.where(y_train == 1, (len(y_train) - pos) / pos, 1.0)
    design = np.column_stack([np.ones(len(x_train)), x_train])
    weights = np.zeros(design.shape[1])
    for _ in range(20):
        linear = np.clip(design @ weights, -20, 20)
        prob = 1 / (1 + np.exp(-linear))
        hess_w = weight * prob * (1 - prob)
        grad = design.T @ (weight * (prob - y_train))
        grad[1:] += l2 * weights[1:]
        fisher = design.T @ (design * hess_w[:, None])
        fisher[1:, 1:] += l2 * np.eye(design.shape[1] - 1)
        step = np.linalg.solve(fisher + 1e-6 * np.eye(design.shape[1]), grad)
        weights -= step
        if np.max(np.abs(step)) < 1e-6:
            break
    return weights


def _predict_logit(weights: np.ndarray, features: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(features)), features])
    linear = np.clip(design @ weights, -20, 20)
    return 1 / (1 + np.exp(-linear))


def _fit_stumps(x_train: np.ndarray, y_train: np.ndarray, rounds: int = 25, rate: float = 0.1):
    """Depth-1 gradient boosting on the logit of a binary label."""
    score = np.zeros(len(y_train))
    stumps = []
    for _ in range(rounds):
        prob = 1 / (1 + np.exp(-np.clip(score, -20, 20)))
        residual = y_train - prob
        best = None
        for col in range(x_train.shape[1]):
            values = x_train[:, col]
            order = np.argsort(values)
            sorted_res = residual[order]
            total = sorted_res.sum()
            csum = np.cumsum(sorted_res)
            gain = np.abs(csum[:-1]) + np.abs(total - csum[:-1])
            if len(gain) == 0:
                continue
            at = int(np.argmax(gain))
            if best is None or gain[at] > best[0]:
                threshold = float(values[order[at]])
                left = float(sorted_res[: at + 1].mean()) if at >= 0 else 0.0
                right = float(sorted_res[at + 1:].mean()) if at + 1 < len(sorted_res) else 0.0
                best = (float(gain[at]), col, threshold, left, right)
        if best is None:
            break
        _, col, threshold, left, right = best
        score += rate * np.where(x_train[:, col] <= threshold, left, right)
        stumps.append((col, threshold, rate * left, rate * right))
    return stumps


def _predict_stumps(stumps, features: np.ndarray) -> np.ndarray:
    score = np.zeros(len(features))
    for col, threshold, left, right in stumps:
        score += np.where(features[:, col] <= threshold, left, right)
    return 1 / (1 + np.exp(-np.clip(score, -20, 20)))


def _score_to_signals(score: np.ndarray, threshold: float, dates, mask: np.ndarray) -> list[tuple[int, int]]:
    bull = _cooldown(np.flatnonzero(mask & (score >= threshold)), dates, 10)
    bear = _cooldown(np.flatnonzero(mask & (score <= -threshold)), dates, 10)
    return [(int(i), 1) for i in bull] + [(int(i), -1) for i in bear]


def simulate_trade(market: dict, i: int, side: int, atr: float) -> dict | None:
    open_ = market["open"]
    high = market["high"]
    low = market["low"]
    close = market["close"]
    day_id = market["day_id"]
    n = len(close)
    entry_i = i + 1
    if entry_i >= n or day_id[entry_i] != day_id[i] or not np.isfinite(atr) or atr <= 0:
        return None
    entry = open_[entry_i] + side * SLIPPAGE
    if entry <= 0:
        return None
    distance = max(0.003 * entry, 3 * atr)
    target = entry + side * distance
    stop = entry - side * distance
    last = entry_i
    exit_price = close[entry_i]
    outcome = "time"
    for j in range(entry_i, min(n, entry_i + HORIZON)):
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
            exit_price = stop
            outcome = "stop"
            break
        if hit_target:
            exit_price = target
            outcome = "target"
            break
        exit_price = close[j]
    pnl = side * (exit_price - entry)
    forward_close = close[last]
    return {
        "pnl": float(pnl),
        "ret": float(pnl / entry),
        "win": bool(pnl > 0),
        "hit": outcome == "target",
        "direction_ok": bool(side * (forward_close - entry) > 0),
    }


def evaluate_signals(market: dict, signals: list[tuple[int, int]], events: list[dict], sessions: set, atr: np.ndarray) -> dict:
    dates = market["dates"]
    kept_events = [event for event in events if event["day"] in sessions]
    by_day_signals: dict = {}
    trades = []
    for i, side in signals:
        if dates[i] not in sessions:
            continue
        trade = simulate_trade(market, i, side, float(atr[i]) if np.isfinite(atr[i]) else np.nan)
        if trade is None:
            continue
        trade.update(i=i, side=side, day=dates[i])
        trades.append(trade)
        by_day_signals.setdefault(dates[i], []).append((i, side, trade))
    caught = []
    leads = []
    for event in kept_events:
        best = None
        for i, side, _trade in by_day_signals.get(event["day"], []):
            if side != event["side"]:
                continue
            lead = (event["onset_i"] - i) * 1.0
            # Decision is the signal bar close, one minute after its start.
            # Lead counts only if that close is before the onset bar starts.
            lead_min = float(event["onset_i"] - (i + 1))
            if lead_min <= 0 or lead_min > 30:
                continue
            if best is None or i < best[0]:
                best = (i, lead_min)
        caught.append(best is not None)
        if best is not None:
            leads.append(best[1])
    session_list = list(sessions)
    fa = []
    hits = []
    wins = []
    correct = []
    pnls = []
    for day in session_list:
        day_trades = [item[2] for item in by_day_signals.get(day, [])]
        fa.append(sum(not item["hit"] for item in day_trades))
        for item in day_trades:
            hits.append(item["hit"])
            wins.append(item["win"])
            correct.append(item["direction_ok"])
            pnls.append(item["pnl"])
    event_days = [event["day"] for event in kept_events]
    return {
        "sessions": len(session_list),
        "events": len(kept_events),
        "signals": len(trades),
        "pre_onset_catch": (sum(caught) / len(kept_events)) if kept_events else None,
        "pre_onset_ci": _boot_rate(event_days, caught, session_list),
        "median_lead_min": float(np.median(leads)) if leads else None,
        "median_lead_ci": _boot_median(event_days, caught, leads, session_list),
        "hit_rate": (sum(hits) / len(hits)) if hits else None,
        "hit_rate_ci": _boot_mean_of_flags(session_list, by_day_signals, "hit"),
        "direction_accuracy": (sum(correct) / len(correct)) if correct else None,
        "direction_accuracy_ci": _boot_mean_of_flags(session_list, by_day_signals, "direction_ok"),
        "false_alarms_per_session": (sum(fa) / len(session_list)) if session_list else None,
        "false_alarms_ci": _boot_counts(session_list, fa),
        "expectancy_per_signal": float(np.mean(pnls)) if pnls else None,
        "expectancy_ci": _boot_trade_mean(session_list, by_day_signals, "pnl"),
        "win_rate": (sum(wins) / len(wins)) if wins else None,
        "win_rate_ci": _boot_mean_of_flags(session_list, by_day_signals, "win"),
        "caught": caught,
        "event_days": event_days,
        "leads": leads,
    }


def _resample(days: list, rng: np.random.Generator):
    pick = rng.choice(len(days), size=len(days), replace=True)
    return [days[i] for i in pick]


def _boot_rate(event_days, caught, sessions, draws=500, seed=16):
    if not event_days:
        return None
    grouped: dict = {}
    for day, flag in zip(event_days, caught):
        grouped.setdefault(day, []).append(flag)
    rng = np.random.default_rng(seed)
    samples = []
    usable = [day for day in sessions if day in grouped]
    if len(usable) < 2:
        return None
    for _ in range(draws):
        chosen = _resample(usable, rng)
        flags = [flag for day in chosen for flag in grouped[day]]
        samples.append(sum(flags) / len(flags))
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def _boot_median(event_days, caught, leads, sessions, draws=500, seed=16):
    grouped: dict = {}
    cursor = 0
    for day, flag in zip(event_days, caught):
        if flag:
            grouped.setdefault(day, []).append(leads[cursor])
            cursor += 1
    usable = [day for day in sessions if day in grouped]
    if len(usable) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        chosen = _resample(usable, rng)
        pool = [value for day in chosen for value in grouped[day]]
        samples.append(float(np.median(pool)))
    return [round(float(np.quantile(samples, 0.025)), 2), round(float(np.quantile(samples, 0.975)), 2)]


def _boot_counts(sessions, values, draws=500, seed=16):
    if not sessions:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    samples = [float(rng.choice(arr, size=len(arr), replace=True).mean()) for _ in range(draws)]
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def _boot_mean_of_flags(sessions, by_day, key, draws=500, seed=16):
    grouped = {day: [item[2][key] for item in rows] for day, rows in by_day.items()}
    usable = [day for day in sessions if grouped.get(day)]
    if len(usable) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        chosen = _resample(usable, rng)
        flags = [flag for day in chosen for flag in grouped[day]]
        samples.append(sum(flags) / len(flags))
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def _boot_trade_mean(sessions, by_day, key, draws=500, seed=16):
    grouped = {day: [item[2][key] for item in rows] for day, rows in by_day.items()}
    usable = [day for day in sessions if grouped.get(day)]
    if len(usable) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        chosen = _resample(usable, rng)
        values = [value for day in chosen for value in grouped[day]]
        samples.append(float(np.mean(values)))
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def _public(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in {"caught", "event_days", "leads"}}


def _separated(candidate_ci, baseline_ci) -> bool:
    return bool(candidate_ci and baseline_ci and candidate_ci[0] > baseline_ci[1])


def promote(candidate: dict, legacy: dict) -> dict:
    catch = _separated(candidate.get("pre_onset_ci"), legacy.get("pre_onset_ci"))
    expectancy = candidate.get("expectancy_ci")
    positive = bool(expectancy and expectancy[0] > 0)
    ok = catch and positive
    return {
        "promote": ok,
        "catch_interval_above_legacy": catch,
        "expectancy_interval_above_zero": positive,
        "reason": "test catch-rate interval is above legacy and expectancy interval is above zero" if ok else "not promoted",
    }


def run(root: Path) -> dict:
    market = prepare(root)
    print(f"loaded SPY bars {len(market['close'])}", flush=True)
    atr_series = five_minute_atr(market["frame"])
    atr = _align(atr_series, market["index"], limit=20)
    events = _events_index(market, build_events(market["frame"], atr_series))
    print(f"events {len(events)}", flush=True)
    sessions = sorted(set(market["dates"]))
    parts = split_60_20_20(sessions)
    rules = rule_signals(market, atr)
    legacy = {
        "legacy_default": _map_legacy(market, legacy_signals(market["frame"])),
        "legacy_15_2_0.25_0.05": _map_legacy(market, legacy_signals(
            market["frame"], lookback=15, rvol_min=2.0, momentum_pct=0.25, min_distance_atr=0.05)),
        "legacy_price_only": _map_legacy(market, legacy_signals(market["frame"], require_volume=False)),
        "legacy_price_only_early": _map_legacy(market, legacy_signals(
            market["frame"], lookback=15, momentum_pct=0.25, min_distance_atr=0.05, require_volume=False)),
    }
    rules.update(legacy)
    features = _features(market, atr)
    labels = _labels(len(market["close"]), events, market["day_id"])
    train_days = set(parts["train"])
    val_days = set(parts["validation"])
    test_days = set(parts["test"])
    train_mask = np.array([day in train_days for day in market["dates"]]) & (market["minutes"] >= 10 * 60)
    val_mask = np.array([day in val_days for day in market["dates"]]) & (market["minutes"] >= 10 * 60)
    mean = features[train_mask].mean(axis=0)
    std = features[train_mask].std(axis=0)
    std[std < 1e-8] = 1
    scaled = (features - mean) / std
    bull = (labels == 1).astype(float)
    bear = (labels == -1).astype(float)
    logit_up = _fit_logit(scaled[train_mask], bull[train_mask])
    logit_down = _fit_logit(scaled[train_mask], bear[train_mask])
    logit_score = _predict_logit(logit_up, scaled) - _predict_logit(logit_down, scaled)
    stumps_up = _fit_stumps(scaled[train_mask], bull[train_mask])
    stumps_down = _fit_stumps(scaled[train_mask], bear[train_mask])
    boost_score = _predict_stumps(stumps_up, scaled) - _predict_stumps(stumps_down, scaled)
    model_choice = {}
    for name, score in (("logit_price", logit_score), ("boost_price", boost_score)):
        best = None
        for threshold in (0.05, 0.10, 0.15, 0.25, 0.40):
            signals = _score_to_signals(score, threshold, market["dates"], val_mask)
            metrics = evaluate_signals(market, signals, events, val_days, atr)
            fa = metrics["false_alarms_per_session"] or 99
            rank = (
                fa <= 6,
                metrics["pre_onset_catch"] or -1,
                metrics["median_lead_min"] if metrics["median_lead_min"] is not None else -999,
                metrics["expectancy_per_signal"] if metrics["expectancy_per_signal"] is not None else -999,
            )
            if best is None or rank > best[0]:
                best = (rank, threshold, metrics)
        model_choice[name] = {"threshold": best[1], "validation": _public(best[2])}
        rules[name] = _score_to_signals(score, best[1], market["dates"], np.ones(len(score), dtype=bool))
    validation = {}
    test = {}
    for name, signals in rules.items():
        if name in model_choice:
            validation[name] = model_choice[name]["validation"]
            continue
        validation[name] = _public(evaluate_signals(market, signals, events, val_days, atr))
    for name, signals in rules.items():
        test[name] = _public(evaluate_signals(market, signals, events, test_days, atr))
    legacy_test = test["legacy_default"]
    decision = {"promote": False, "name": None, "reason": "no candidate beat legacy outside the interval with expectancy above zero"}
    order = sorted(
        (name for name in validation if name != "legacy_default"),
        key=lambda name: (
            validation[name].get("pre_onset_catch") or -1,
            validation[name].get("median_lead_min") if validation[name].get("median_lead_min") is not None else -999,
        ),
        reverse=True,
    )
    for name in order:
        verdict = promote(test[name], legacy_test)
        if verdict["promote"]:
            decision = {"promote": True, "name": name, **verdict}
            break
    return {
        "data": {
            "root": str(root),
            "spy_bars": int(len(market["close"])),
            "sessions": len(sessions),
            "first": sessions[0].isoformat(),
            "last": sessions[-1].isoformat(),
            "volume": "Dukascopy CFD volume, not exchange volume. RVOL is self-relative only.",
            "vix": "Dukascopy volatility CFD, not official CBOE VIX. VIX1D covers 17 sessions and is not a model feature.",
            "price": "bid",
        },
        "split": {name: [day.isoformat() for day in days] for name, days in parts.items()},
        "split_counts": {name: len(days) for name, days in parts.items()},
        "events": len(events),
        "validation": validation,
        "model_validation": model_choice,
        "test": test,
        "promotion": decision,
        "live_default": "legacy_default" if not decision["promote"] else decision["name"],
    }


def markdown(report: dict) -> str:
    lines = [
        "# دراسة 22 شهرًا — كشف الانفجار المبكر",
        "",
        f"الحكم: **{'READY ' + report['promotion']['name'] if report['promotion']['promote'] else 'NOT READY'}**.",
        "التنبيه الحي يبقى القاعدة القديمة ما لم ينجح مرشح على الاختبار بفاصل ثقة أعلى من القديم وتوقع ربح موجب.",
        "",
        f"SPY من {report['data']['first']} إلى {report['data']['last']}، {report['data']['sessions']} جلسة، {report['data']['spy_bars']} شمعة.",
        f"التقسيم: تدريب {report['split_counts']['train']}، تحقق {report['split_counts']['validation']}، اختبار {report['split_counts']['test']}.",
        "حجم Dukascopy حجم وسيط CFD وليس حجم البورصة. VIX هنا عقد فروقات ضعيف وليس VIX الرسمي.",
        "الدخول في افتتاح الشمعة التالية مع انزلاق سنت واحد. الخروج عند الهدف أو الوقف أو 30 دقيقة.",
        "",
        "| القاعدة | التقاط قبل البداية | فترة 95% | وسيط السبق | إصابة 30د | دقتها | كاذبة/جلسة | توقع$/إشارة | فوز |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, row in report["test"].items():
        lines.append(
            f"| {name} | {row['pre_onset_catch']} | {row['pre_onset_ci']} | {row['median_lead_min']} | "
            f"{row['hit_rate']} | {row['direction_accuracy']} | {row['false_alarms_per_session']} | "
            f"{row['expectancy_per_signal']} | {row['win_rate']} |"
        )
    lines.append("")
    lines.append(f"الترقية: {report['promotion']['reason']}.")
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Long-sample explosion study")
    parser.add_argument("--root", default="data/archive/dukascopy/spx_history")
    parser.add_argument("--output", default="artifacts/explosion_long/report.json")
    args = parser.parse_args()
    report = run(Path(args.root))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report_md = destination.with_suffix(".md")
    report_md.write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    print("PROMOTE", report["promotion"]["promote"], report["promotion"].get("name"))


if __name__ == "__main__":
    main()
