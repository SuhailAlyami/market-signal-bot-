#!/usr/bin/env python3
"""
early_move_eval.py  (v2) -- per-instrument audit + minimal walk-forward model vs matched baselines.

RESEARCH ONLY. All samples were used in earlier research; nothing here is an independent holdout.
Underlying-OHLC direction success says nothing about SPX options P&L.

Target (decision at close of bar t, entry = close[t]):
  long  succeeds if high >= entry+2*ATR_t before low <= entry-1*ATR_t within the next 5 one-minute bars
  short is symmetric.  A bar touching BOTH barriers first = AMBIGUOUS (order unknown):
     conservative score = fail, optimistic score = success; both are reported.
ATR modes (separate experiments):
  prior20 : simple mean of the 20 true ranges BEFORE the decision bar (bars t-20..t-1)   <- README / original target
  wilder14: Wilder ATR(14) INCLUDING the decision bar                                      <- earlier harness version
Gaps: a "gap" is any step between consecutive bars != 60 s. Nothing is forward-filled.
  Bars are UNSCORABLE (counted by reason, never silently dropped) when:
    lookback_or_warmup : <21 contiguous prior bars in the same segment (ATR + feature lookback)
    zero_atr           : ATR <= 0
    horizon_gap        : any of the next 5 steps is not exactly 60 s
    end_of_data        : fewer than 5 future bars exist
Signals are generated causally on every bar with a valid lookback (no future info used to pick bars);
signals that land on unscorable bars are counted separately and excluded from precision.

Run:  python early_move_eval.py --data-dir data --out results
"""
import argparse, hashlib, json, math, os, tempfile
import numpy as np, pandas as pd

H, TP, SL = 5, 2.0, 1.0
LOOKBACK = 21
STATUS = {0: "scorable", 1: "lookback_or_warmup", 2: "zero_atr", 3: "horizon_gap", 4: "end_of_data"}
PARAMS = {"SPX": (400, 100), "ES": (9000, 3000), "NQ": (9000, 3000)}   # (min_train_bars, test_block_bars)


# ------------------------------------------------------------------ load / structure / gaps
def load(path):
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    raw["ts"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
    info = dict(rows_raw=len(raw), bad_timestamps=int(raw.ts.isna().sum()))
    raw = raw.dropna(subset=["ts"])
    info["non_monotonic_steps"] = int((raw.ts.diff().dt.total_seconds() < 0).sum())
    raw = raw.sort_values("ts", kind="stable")
    info["duplicate_timestamps_dropped"] = int(raw.ts.duplicated().sum())
    raw = raw.drop_duplicates("ts", keep="first")
    for c in ("open", "high", "low", "close"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    bad = (raw[["open", "high", "low", "close"]].isna().any(axis=1) | (raw.high < raw[["open", "close"]].max(axis=1))
           | (raw.low > raw[["open", "close"]].min(axis=1)) | (raw.high < raw.low))
    info["inconsistent_ohlc_rows_dropped"] = int(bad.sum())      # dropping makes a visible gap, not a fill
    raw = raw[~bad].reset_index(drop=True)
    info["zero_range_bars"] = int((raw.high == raw.low).sum())
    if "volume" in raw:
        info["zero_volume_bars"] = int((raw.volume == 0).sum())
    info.update(rows_used=len(raw), first_ts=str(raw.ts.iloc[0]), last_ts=str(raw.ts.iloc[-1]))
    return raw, info


def add_structure(d):
    d = d.copy()
    d["gap_s"] = d.ts.diff().dt.total_seconds()
    d["seg"] = (d.gap_s.ne(60)).cumsum()
    d["pos"] = d.groupby("seg").cumcount()
    return d


def gaps_table(d):
    rows = []
    for i in d.index[d.gap_s > 60]:
        miss = int(round(d.gap_s[i] / 60)) - 1
        cat = ("1_min" if miss == 1 else "2-5_min" if miss <= 5 else "6-29_min" if miss < 30 else "30+_min(break/overnight/weekend)")
        rows.append(dict(last_bar_before=str(d.ts[i - 1]), first_bar_after=str(d.ts[i]), missing_minutes=miss, category=cat))
    return pd.DataFrame(rows, columns=["last_bar_before", "first_bar_after", "missing_minutes", "category"])


def daily_coverage(d):
    g = d.groupby(d.ts.dt.date).ts
    return {str(k): dict(bars=int(len(v)), first_utc=v.iloc[0].strftime("%H:%M"), last_utc=v.iloc[-1].strftime("%H:%M"))
            for k, v in g}


# ------------------------------------------------------------------ ATR + labels
def add_atr(d, mode):
    d = d.copy()
    pc = d.groupby("seg").close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    if mode == "prior20":
        d["atr"] = tr.groupby(d.seg).transform(lambda s: s.shift(1).rolling(20).mean())
    elif mode == "wilder14":
        d["atr"] = tr.groupby(d.seg).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean())
    else:
        raise ValueError(mode)
    return d


def label(d, entry="close"):
    n = len(d)
    o, h, l, c, a = (d[k].values for k in ("open", "high", "low", "close", "atr"))
    pos, step_ok, ts = d.pos.values, (d.gap_s.values == 60), d.ts
    status = np.zeros(n, int)
    L = {k: np.zeros(n, bool) for k in ("up_c", "up_o", "up_amb", "dn_c", "dn_o", "dn_amb")}
    L["up_k"], L["dn_k"] = np.full(n, np.nan), np.full(n, np.nan)
    amb_rows = []
    for t in range(n):
        if pos[t] < LOOKBACK or not np.isfinite(a[t]): status[t] = 1; continue
        if a[t] <= 0: status[t] = 2; continue
        if t + H >= n: status[t] = 4; continue
        if not step_ok[t + 1:t + H + 1].all(): status[t] = 3; continue
        e, r = (c[t] if entry == "close" else o[t + 1]), a[t]
        for side, nm in ((1, "up"), (-1, "dn")):
            for k in range(1, H + 1):
                b = t + k
                # Opening print precedes both intrabar extrema.
                opening_hit = o[b] >= e + TP * r if side == 1 else o[b] <= e - TP * r
                opening_stop = o[b] <= e - SL * r if side == 1 else o[b] >= e + SL * r
                if opening_hit:
                    L[nm + "_c"][t] = L[nm + "_o"][t] = True; L[nm + "_k"][t] = k; break
                if opening_stop: break
                hit, stop = ((h[b] >= e + TP * r, l[b] <= e - SL * r) if side == 1
                             else (l[b] <= e - TP * r, h[b] >= e + SL * r))
                if hit and stop:
                    L[nm + "_amb"][t] = True; L[nm + "_o"][t] = True; L[nm + "_k"][t] = k
                    amb_rows.append(dict(decision_ts=str(ts[t]), side="long" if side == 1 else "short", bar_k=k,
                                         entry=e, atr=r, target=e + side * TP * r, stop=e - side * SL * r,
                                         bar_high=h[b], bar_low=l[b]))
                    break
                if hit:
                    L[nm + "_c"][t] = L[nm + "_o"][t] = True; L[nm + "_k"][t] = k; break
                if stop: break
    L["status"] = status
    L["amb_rows"] = amb_rows
    return L


# ------------------------------------------------------------------ features / causality
def features(d, canary=False):
    c, h, l, a = d.close, d.high, d.low, d.atr
    F = pd.DataFrame(index=d.index)
    for k in (1, 3, 5, 15): F[f"r{k}"] = (c - c.shift(k)) / a
    F["rng"] = (h - l) / a
    F["cpos"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5)
    if canary: F["canary"] = (c.shift(-1) - c) / a            # deliberate look-ahead (self-test only)
    return F                                                   # no volume: SPX has none; kept identical across tools


def causality_check(d0, mode, canary, n_checks=12, seed=0):
    base = d0[["ts", "open", "high", "low", "close"]]
    full = features(add_atr(add_structure(base), mode), canary)
    rng, bad = np.random.default_rng(seed), 0
    for t in rng.integers(300, len(base) - 1, n_checks):
        sub = features(add_atr(add_structure(base.iloc[:t + 1]), mode), canary).iloc[-1].values
        bad += not np.allclose(sub, full.iloc[t].values, equal_nan=True, rtol=1e-9, atol=1e-12)
    return int(bad), n_checks


# ------------------------------------------------------------------ model
def fit_logit(X, y, l2=5.0, iters=30):
    Xb = np.c_[np.ones(len(X)), X]
    w = np.zeros(Xb.shape[1]); R = np.eye(len(w)) * l2; R[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Xb @ w, -30, 30)))
        w -= np.linalg.solve((Xb * (p * (1 - p))[:, None]).T @ Xb + R + 1e-9 * np.eye(len(w)), Xb.T @ (p - y) + R @ w)
    return w


def predict(w, X): return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


def walk_forward(F, d, lab, min_train, block, q):
    n = len(F); X = F.values; idx = np.arange(n)
    fin = np.isfinite(X).all(1) & (d.pos.values >= LOOKBACK)
    scor = lab["status"] == 0
    sc = np.full((n, 2), np.nan); thr = np.full(n, np.nan); tm = np.zeros(n, bool)
    s = min_train
    while s < n:
        e = min(s + block, n)
        tr = np.where(fin & scor & (idx < s - H))[0]          # purge: train labels must end before test starts
        te = np.where(fin & (idx >= s) & (idx < e))[0]        # test bars: past-only features, no label needed
        if len(tr) > 200 and len(te):
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-12
            Xt, Xe = (X[tr] - mu) / sd, (X[te] - mu) / sd
            wu, wd = fit_logit(Xt, lab["up_c"][tr].astype(float)), fit_logit(Xt, lab["dn_c"][tr].astype(float))
            thr[te] = np.quantile(np.maximum(predict(wu, Xt), predict(wd, Xt)), 1 - q)   # TRAIN-only threshold
            sc[te, 0], sc[te, 1] = predict(wu, Xe), predict(wd, Xe)
            tm[te] = True
        s = e
    sig, dr, scr, last = [], [], [], -10 ** 9
    for t in np.where(tm)[0]:
        if max(sc[t]) >= thr[t] and t - last >= H:
            sig.append(t); dr.append(1 if sc[t, 0] >= sc[t, 1] else -1); scr.append(max(sc[t])); last = t
    return np.array(sig, int), np.array(dr, int), np.array(scr), tm, sc, thr


# ------------------------------------------------------------------ statistics
def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"),) * 2
    p = k / n; dn = 1 + z * z / n; c = (p + z * z / (2 * n)) / dn
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / dn
    return c - r, c + r


def min_k_sig(n, p0, alpha=0.05):
    if n == 0 or not 0 < p0 < 1: return None
    pm = [math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p0) + (n - k) * math.log(1 - p0))
          for k in range(n + 1)]
    tail = 0.0
    for k in range(n, -1, -1):
        tail += pm[k]
        if tail > alpha: return k + 1 if k < n else None
    return 0


def evaluate(F, d, lab, sig, dr, tm, B=2000, seed=1):
    rng = np.random.default_rng(seed)
    scor = lab["status"] == 0; up, dn = lab["up_c"], lab["dn_c"]
    tv = tm & scor
    base = 0.5 * (up[tv].mean() + dn[tv].mean()) if tv.any() else float("nan")
    st = lab["status"][sig] if len(sig) else np.array([], int)
    out = dict(test_bars_scorable=int(tv.sum()), test_bars_unscorable=int((tm & ~scor).sum()),
               test_unscorable_by_reason={STATUS[k]: int(((lab["status"] == k) & tm).sum()) for k in (1, 2, 3, 4)},
               signals_generated=int(len(sig)),
               signals_unscorable={STATUS[k]: int((st == k).sum()) for k in (1, 2, 3, 4)},
               base_rate_random_direction=base)
    keep = st == 0; sg, dd = sig[keep], dr[keep]; m = len(sg); out["signals_scored"] = m
    if m == 0: return out
    pick = lambda U, D, i, s: np.where(s > 0, U[i], D[i])
    hit = pick(up, dn, sg, dd); k = int(hit.sum()); lo, hi = wilson(k, m)
    out.update(hits_conservative=k, precision_conservative=k / m, ci95_conservative=[lo, hi],
               precision_optimistic=float(pick(lab["up_o"], lab["dn_o"], sg, dd).mean()),
               ambiguous_signals=int(pick(lab["up_amb"], lab["dn_amb"], sg, dd).sum()),
               min_hits_for_p05_vs_base=min_k_sig(m, base))
    day = d.ts.dt.floor("D").values.astype("datetime64[D]")[sg]       # cluster (day-block) bootstrap CI
    ud, inv = np.unique(day, return_inverse=True)
    hc, nc = np.bincount(inv, weights=hit.astype(float)), np.bincount(inv)
    bi = rng.integers(0, len(ud), (B, len(ud)))
    bp = hc[bi].sum(1) / nc[bi].sum(1)
    ac = float(np.corrcoef(hit[:-1], hit[1:])[0, 1]) if m > 2 and hit.std() > 0 else None
    out.update(days_with_signals=int(len(ud)), ci95_dayblock_bootstrap=[float(np.quantile(bp, .025)), float(np.quantile(bp, .975))],
               lag1_autocorr_of_signal_outcomes=ac)
    D = rng.choice([-1, 1], (B, m))                                   # B1: same bars, random direction
    b1 = np.where(D > 0, up[sg][None], dn[sg][None]).mean(1)
    tpos = np.where(tm)[0]; N = len(tpos); p = np.searchsorted(tpos, sg)   # B2: same signal series, circularly shifted
    i2 = tpos[(p[None] + rng.integers(1, N, B)[:, None]) % N]; v2 = scor[i2]
    b2 = (np.where(dd[None] > 0, up[i2], dn[i2]) & v2).sum(1) / np.maximum(v2.sum(1), 1)
    ms = np.sign(F["r5"].values[sg]); mk = ms != 0                  # B3: momentum sign at same bars
    out.update(baseline_dirshuffle_mean=float(b1.mean()), p_vs_dirshuffle=float((1 + (b1 >= k / m).sum()) / (B + 1)),
               baseline_timeshift_mean=float(b2.mean()), p_vs_timeshift=float((1 + (b2 >= k / m).sum()) / (B + 1)),
               baseline_momentum_sign=float(pick(up, dn, sg[mk], ms[mk]).mean()) if mk.any() else None)
    ev_tot = ev_det = 0; late, kto, runs = [], [], []
    for side, arr, kk in ((1, up, lab["up_k"]), (-1, dn, lab["dn_k"])):
        s_ = arr & tm; stt = s_ & ~np.r_[False, s_[:-1]]
        rid = np.cumsum(stt) * s_; starts = np.where(stt)[0]; ev_tot += len(starts)
        g = sg[dd == side]; ids = rid[g]; first = {}
        for t, i in zip(g[ids > 0], ids[ids > 0]): first[i] = min(first.get(i, 10 ** 9), t)
        rl = np.bincount(rid[rid > 0])[1:]; runs.extend(rl.tolist())
        ev_det += len(first); late += [first[i] - starts[i - 1] for i in first]
        kto += [kk[t] for t in g[ids > 0]]
    out.update(event_run_length_median=float(np.median(runs)) if runs else None,
               event_share_of_length_1=float(np.mean(np.array(runs) == 1)) if runs else None, events=ev_tot, events_detected=ev_det, event_recall=ev_det / ev_tot if ev_tot else None,
               median_lateness_bars=float(np.median(late)) if late else None,
               mean_bars_to_2ATR=float(np.nanmean(kto)) if kto else None)
    return out


def q_audit(F, d, lab, sc, thr, tm, sig, min_train, block, q, seed=7):
    """(a) realized fire rate vs q; (b) corrupt ALL rows from fold-3 start onward (features+labels permuted) and
    check thresholds/scores for earlier rows and fold-3's own threshold are unchanged => train-only dependence."""
    n = len(F); s0 = min(min_train + 2 * block, n - block)
    pre = float(((np.fmax(sc[:, 0], sc[:, 1]) >= thr) & tm).sum() / max(tm.sum(), 1))
    rng = np.random.default_rng(seed); perm = rng.permutation(np.arange(s0, n))
    F2 = F.copy(); F2.iloc[s0:] = F.values[perm]
    lab2 = {k: v.copy() for k, v in lab.items() if isinstance(v, np.ndarray)}
    for k in lab2: lab2[k][s0:] = lab[k][perm]
    _, _, _, _, sc2, thr2 = walk_forward(F2, d, lab2, min_train, block, q)
    same_prev = bool(np.array_equal(thr[:s0], thr2[:s0], equal_nan=True) and np.array_equal(sc[:s0], sc2[:s0], equal_nan=True))
    j = slice(s0, min(s0 + block, n)); a_, b_ = np.nanmedian(thr[j]), np.nanmedian(thr2[j])
    return dict(q=q, fire_rate_precooldown_test=pre, fire_rate_after_cooldown_test=float(len(sig) / max(tm.sum(), 1)),
                corrupted_from_row=int(s0), earlier_thresholds_and_scores_identical=same_prev,
                fold3_threshold_original=float(a_), fold3_threshold_with_corrupted_future=float(b_),
                fold3_threshold_identical=bool(np.isclose(a_, b_, rtol=0, atol=1e-12)))


def signals_df(d, lab, sig, dr, scr):
    rows = []
    for t, s, x in zip(sig, dr, scr):
        nm = "up" if s > 0 else "dn"; stt = int(lab["status"][t])
        rows.append(dict(decision_ts=str(d.ts[t]), direction="long" if s > 0 else "short", score=round(float(x), 4),
                         status=STATUS[stt], success_conservative=bool(lab[nm + "_c"][t]) if stt == 0 else None,
                         success_optimistic=bool(lab[nm + "_o"][t]) if stt == 0 else None,
                         ambiguous=bool(lab[nm + "_amb"][t]) if stt == 0 else None,
                         bars_to_target=None if stt or np.isnan(lab[nm + "_k"][t]) else int(lab[nm + "_k"][t])))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ driver
def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=lambda x: x.item() if hasattr(x, "item") else str(x))


def run_instrument(sym, path, out, modes, q, canary, min_train, block, sha_expected=None, entry="close"):
    raw, info = load(path)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    d0 = add_structure(raw)
    gaps = gaps_table(d0); gaps.to_csv(f"{out}/{sym}_gaps.csv", index=False)
    audit = dict(symbol=sym, sha256=sha, sha256_matches_manifest=(None if sha_expected is None else sha == sha_expected),
                 load=info, gap_count=int(len(gaps)), gaps_by_category=gaps.category.value_counts().to_dict(),
                 missing_minutes_total=int(gaps.missing_minutes.sum()) if len(gaps) else 0,
                 daily_coverage_utc=daily_coverage(d0))
    jdump(audit, f"{out}/{sym}_data_audit.json")
    labs, ds, res_all = {}, {}, {}
    for mode in modes:
        d = add_atr(d0, mode); lab = label(d, entry); F = features(d, canary)
        bad, nchk = causality_check(d0, mode, canary)
        sig, dr, scr, tm, sc_, thr_ = walk_forward(F, d, lab, min_train, block, q)
        ev = evaluate(F, d, lab, sig, dr, tm)
        qa = q_audit(F, d, lab, sc_, thr_, tm, sig, min_train, block, q)
        sc = lab["status"] == 0
        res = dict(symbol=sym, atr_mode=mode, entry=entry, q=q, min_train=min_train, test_block=block,
                   causality_failures=f"{bad}/{nchk}", bars=len(d),
                   status_counts_all_bars={STATUS[k]: int((lab["status"] == k).sum()) for k in STATUS},
                   base_rate_long=float(lab["up_c"][sc].mean()), base_rate_short=float(lab["dn_c"][sc].mean()),
                   ambiguous_bars_long=int(lab["up_amb"].sum()), ambiguous_bars_short=int(lab["dn_amb"].sum()),
                   q_audit=qa, **ev)
        jdump(res, f"{out}/{sym}_{mode}_results.json")
        pd.DataFrame(lab["amb_rows"]).to_csv(f"{out}/{sym}_{mode}_ambiguous_cases.csv", index=False)
        signals_df(d, lab, sig, dr, scr).to_csv(f"{out}/{sym}_{mode}_signals.csv", index=False)
        labs[mode], ds[mode], res_all[mode] = lab, d, res
    cmp_ = None
    if "prior20" in labs and "wilder14" in labs:
        A, B_ = labs["prior20"], labs["wilder14"]; both = (A["status"] == 0) & (B_["status"] == 0)
        ratio = (ds["wilder14"].atr / ds["prior20"].atr)[both]
        cmp_ = dict(symbol=sym, scorable_prior20=int((A["status"] == 0).sum()), scorable_wilder14=int((B_["status"] == 0).sum()),
                    atr14_over_atr20_ratio_p5_median_p95=[float(x) for x in ratio.quantile([.05, .5, .95])],
                    long_label_agreement=float((A["up_c"] == B_["up_c"])[both].mean()),
                    short_label_agreement=float((A["dn_c"] == B_["dn_c"])[both].mean()),
                    base_rate_long=[float(A["up_c"][both].mean()), float(B_["up_c"][both].mean())],
                    base_rate_short=[float(A["dn_c"][both].mean()), float(B_["dn_c"][both].mean())],
                    note="pairs are [prior20, wilder14]")
    return audit, res_all, cmp_


def synth(n, seed, phi=0.0, drop=0.01):
    rng = np.random.default_rng(seed); ls = np.zeros(n)
    for i in range(1, n): ls[i] = 0.98 * ls[i - 1] + 0.1 * rng.standard_normal()
    sg = 0.0004 * np.exp(ls); r = sg * rng.standard_normal(n)
    for i in range(1, n): r[i] += phi * r[i - 1]
    sub = rng.standard_normal((n, 6)) * sg[:, None] / math.sqrt(6)
    sub = sub - sub.mean(1, keepdims=True) + r[:, None] / 6
    p = np.exp(np.log(4500) + np.cumsum(sub.ravel()).reshape(n, 6)); prev = np.r_[4500.0, p[:-1, -1]]
    df = pd.DataFrame(dict(timestamp=pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC"), open=prev,
                           high=np.maximum(p.max(1), prev), low=np.minimum(p.min(1), prev), close=p[:, -1]))
    return df[rng.random(n) > drop].reset_index(drop=True)          # random missing minutes -> exercises gap logic


def selftest():
    print("SELF-TEST (synthetic; validates harness only, NOT market evidence)")
    tmp = tempfile.mkdtemp()
    for name, df, can in (("noise", synth(30000, 1), False), ("noise+LOOKAHEAD canary", synth(30000, 1), True),
                          ("planted AR(1) phi=0.25", synth(30000, 2, 0.25), False)):
        p = f"{tmp}/s.csv"; df.to_csv(p, index=False)
        _, r, _ = run_instrument("S", p, tmp, ["prior20"], 0.02, can, 10000, 4000)
        r = r["prior20"]
        print(f"{name:26s} prec={r.get('precision_conservative', float('nan')):.3f} base={r['base_rate_random_direction']:.3f} "
              f"dirshuffle={r.get('baseline_dirshuffle_mean', float('nan')):.3f} p_dir={r.get('p_vs_dirshuffle')} "
              f"causality_fail={r['causality_failures']} unscorable_sig={r['signals_unscorable']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data"); ap.add_argument("--out", default="results")
    ap.add_argument("--instruments", nargs="+", default=["SPX", "ES", "NQ"])
    ap.add_argument("--atr", nargs="+", default=["prior20", "wilder14"], help="first = primary, others = separate experiments")
    ap.add_argument("--q", type=float, default=0.02); ap.add_argument("--entry", choices=["close", "next_open"], default="close")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: selftest(); raise SystemExit
    os.makedirs(a.out, exist_ok=True)
    man = {m["symbol"]: m["sha256"] for m in json.load(open(f"{a.data_dir}/manifest.json"))} if os.path.exists(f"{a.data_dir}/manifest.json") else {}
    cmps, summ = [], {}
    for sym in a.instruments:
        mt, bl = PARAMS[sym]
        au, rs, cm = run_instrument(sym, f"{a.data_dir}/{sym}_1m.csv", a.out, a.atr, a.q, False, mt, bl, man.get(sym), a.entry)
        summ[sym] = rs; cmps.append(cm) if cm else None
        print(f"\n[{sym}] sha_ok={au['sha256_matches_manifest']} rows={au['load']['rows_used']} gaps={au['gap_count']} "
              f"missing_min={au['missing_minutes_total']} {au['gaps_by_category']}")
        for mode, r in rs.items():
            print(f"  {mode:8s} unscorable={ {k: v for k, v in r['status_counts_all_bars'].items() if k != 'scorable'} } "
                  f"amb(L/S)={r['ambiguous_bars_long']}/{r['ambiguous_bars_short']} base(L/S)={r['base_rate_long']:.3f}/{r['base_rate_short']:.3f} "
                  f"causality_fail={r['causality_failures']}")
            print(f"           signals={r['signals_generated']} scored={r['signals_scored']} unscorable_sig={r['signals_unscorable']} "
                  f"prec_cons={r.get('precision_conservative')} prec_opt={r.get('precision_optimistic')} amb_sig={r.get('ambiguous_signals')}")
            print(f"           base_rand_dir={r['base_rate_random_direction']:.3f} dirshuffle={r.get('baseline_dirshuffle_mean')} "
                  f"timeshift={r.get('baseline_timeshift_mean')} mom={r.get('baseline_momentum_sign')} "
                  f"p_dir={r.get('p_vs_dirshuffle')} p_time={r.get('p_vs_timeshift')} min_hits_p05={r.get('min_hits_for_p05_vs_base')}")
            print(f"           events={r.get('events')} detected={r.get('events_detected')} recall={r.get('event_recall')} "
                  f"median_lateness={r.get('median_lateness_bars')} mean_bars_to_target={r.get('mean_bars_to_2ATR')}")
    fam = [(sym, t, summ[sym][a.atr[0]].get(t)) for sym in a.instruments for t in ("p_vs_dirshuffle", "p_vs_timeshift")]
    fam = [x for x in fam if x[2] is not None]; order = sorted(range(len(fam)), key=lambda i: fam[i][2]); run_max, holm = 0.0, {}
    for r_, i in enumerate(order):
        run_max = max(run_max, min(1.0, (len(fam) - r_) * fam[i][2])); holm[f"{fam[i][0]}:{fam[i][1]}"] = dict(raw=fam[i][2], holm_adjusted=run_max)
    jdump(dict(primary_atr_mode=a.atr[0], family_size=len(fam), tests=holm), f"{a.out}/significance_holm.json")
    jdump(cmps, f"{a.out}/atr_comparison.json"); jdump(summ, f"{a.out}/summary.json")
    print("\nATR comparison:", json.dumps(cmps))
