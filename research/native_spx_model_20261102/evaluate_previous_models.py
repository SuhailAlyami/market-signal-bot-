#!/usr/bin/env python3
"""
evaluate_previous_models.py -- unified evaluation of the 18 earlier Suhail Python models + v4 WATCH lifecycle.

EXPLORATORY / RESEARCH ONLY. Every sample was consumed by earlier research; the train/test split below is
a temporal convention, NOT a clean independent holdout.

Unified success rule (early_move_eval_openfix.py, ATR20 prior): signal at close of bar t succeeds if price reaches
2xATR before an adverse 1xATR within 5 one-minute bars. Same-bar ambiguity: conservative=fail, optimistic=success
(openfix: an opening print beyond a barrier decides first). Entry: close[t] (primary) or open[t+1] (robustness).

Stages (run in order; stage 2 refuses to run unless the stage-1 lock file verifies):
  stage1 : ES/NQ TRAIN only (2026-09-21..10-05, purged by 5 bars). Model table, failure analysis, four pre-declared
           candidate contrasts, one-hypothesis selection by a fixed rule -> HYPOTHESIS_LOCKED.json (+ .sha256)
  stage2 : everything else (test period 10-06..10-18, full period, SPX descriptive), Holm correction, and the
           frozen hypothesis test. No parameter or rule is changed after stage 1.
"""
import argparse, hashlib, importlib.util, json, os, zlib
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("ev", HERE / "early_move_eval_openfix.py")
EV = importlib.util.module_from_spec(_s); _s.loader.exec_module(EV)
H, SL, STATUS = EV.H, EV.SL, EV.STATUS
FIRST_TEST = date(2026, 10, 6)
MODELS18 = ["v4_impulse", "v3_ready", "failed_break", "range_break10", "trend_pullback", "rsi_reentry",
            "confirmed_divergence", "double_bottom_top", "flag_contraction", "head_shoulders", "inverse_head_shoulders",
            "macd_cross", "macd_trend", "macd_trend_body", "break_retest", "retest_macd", "macd_trend_rsi", "retest_macd_rsi"]
CANDS = {   # fixed BEFORE any outcome was inspected; mechanism text is part of the declaration
    "F1_range_expansion": ("decision-bar range >= 1.0 x ATR20(prior)",
                           "Success needs a 2xATR extension in 5 min; a signal bar that already expands range marks a regime where that extension is reachable."),
    "F2_trend_aligned": ("direction equals sign of the 15-bar close change",
                         "Very short-horizon momentum persistence would favour with-trend signals over counter-trend ones."),
    "F3_candle_aligned": ("direction equals sign(close-open) of the decision bar",
                          "A signal that contradicts its own bar body is a fade; with-body signals carry the bar's impulse."),
    "F4_us_cash_hours": ("bar-start time 13:30-19:59 UTC",
                         "Cash-session liquidity gives larger 1-minute ranges than overnight, so 2xATR within 5 min is reached more often."),
}


# ------------------------------------------------------------------ data / signals
def prep(sym, data_dir, exp_dir):
    raw, info = EV.load(f"{data_dir}/{sym}_1m.csv")
    d = EV.add_atr(EV.add_structure(raw), "prior20")
    em = json.load(open(f"{exp_dir}/export_manifest.json"))[sym]
    assert len(d) == em["rows"], (sym, len(d), em["rows"])
    sig = pd.read_csv(f"{exp_dir}/{sym}_signals.csv")
    ts = pd.to_datetime(sig.bar_timestamp_utc, utc=True)
    assert (d.ts.iloc[sig.bar_index.values].values == ts.values).all(), "bar_index/timestamp misalignment"
    wl = pd.read_csv(f"{exp_dir}/{sym}_v4_watch_lifecycle.csv")
    wl = wl[wl.event.isin(["UP", "DOWN"])]
    labs = {e: EV.label(d, e) for e in ("close", "next_open")}
    return d, labs, sig, wl


def signal_sets(d, sig, wl):
    out = {}
    secs = (d.ts - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().values   # unit-safe (pandas may store us/ns)
    for model, g in sig.groupby("model", sort=False):
        g = g.sort_values("bar_index"); idx = g.bar_index.values; dr = np.where(g.direction.values == "long", 1, -1)
        out[(model, "raw")] = (idx, dr)
        k = g.cooldown_10m_selected.values == 1; out[(model, "cd10")] = (idx[k], dr[k])
        keep, last = [], -10 ** 9
        for j, t in enumerate(idx):
            if t - last >= H: keep.append(j); last = t
        out[(model, "cd5")] = (idx[keep], dr[keep])
    idx = wl.bar_index.values; dr = np.where(wl.event.values == "UP", 1, -1)
    out[("v4_watch", "as_exported")] = (idx, dr)
    keep, last = [], -10 ** 12
    for j, t in enumerate(idx):
        if secs[t] - last >= 600: keep.append(j); last = secs[t]
    out[("v4_watch", "cd10")] = (idx[keep], dr[keep])
    return out


def periods(d, sym):
    n = len(d)
    if sym == "SPX": return {"full": np.ones(n, bool)}
    ft = int(np.argmax(d.ts.dt.date.values >= FIRST_TEST)); r = np.arange(n)
    return {"train": r + H < ft, "test": r >= ft, "full": np.ones(n, bool)}


def sig_features(d, idx, dr):
    c, o, h, l, a = (d[k].values for k in ("close", "open", "high", "low", "atr"))
    mod = d.ts.dt.hour.values * 60 + d.ts.dt.minute.values
    return {"F1_range_expansion": (h[idx] - l[idx]) / a[idx] >= 1.0,
            "F2_trend_aligned": np.sign(c[idx] - c[idx - 15]) == dr,
            "F3_candle_aligned": np.sign(c[idx] - o[idx]) == dr,
            "F4_us_cash_hours": (mod[idx] >= 13 * 60 + 30) & (mod[idx] < 20 * 60)}


def outcome_class(d, lab, idx, dr):
    h, l, c, a = (d[k].values for k in ("high", "low", "close", "atr")); res = []
    for t, s in zip(idx, dr):
        nm = "up" if s > 0 else "dn"
        if lab[nm + "_c"][t]: res.append("target"); continue
        if lab[nm + "_amb"][t]: res.append("ambiguous"); continue
        r = a[t]; w = slice(t + 1, t + H + 1)
        stop = l[w].min() <= c[t] - SL * r if s > 0 else h[w].max() >= c[t] + SL * r
        res.append("stop_hit" if stop else "timeout")
    return np.array(res)


# ------------------------------------------------------------------ scoring
def score_set(idx, dr, lab, dates, mask, key, B=2000):
    rng = np.random.default_rng(zlib.crc32(key.encode()))
    status, up, dn = lab["status"], lab["up_c"], lab["dn_c"]; scor = status == 0
    tv = mask & scor; nb = int(tv.sum())
    out = dict(scorable_bars=nb, base_rate=float(0.5 * (up[tv].mean() + dn[tv].mean())) if nb else np.nan)
    sel = mask[idx]; idx, dr = idx[sel], dr[sel]; st = status[idx]
    out["n_signals"] = int(len(idx))
    for k in (1, 2, 3, 4): out["unscorable_" + STATUS[k]] = int((st == k).sum())
    keep = st == 0; sg, dd = idx[keep], dr[keep]; m = len(sg); out["n_scored"] = m
    out["signals_per_1000_bars"] = 1000 * m / nb if nb else np.nan
    out["days"] = int(len(np.unique(dates[mask])))
    if m == 0: return out
    pick = lambda U, D, i, s: np.where(s > 0, U[i], D[i])
    hit = pick(up, dn, sg, dd); k = int(hit.sum()); lo, hi = EV.wilson(k, m)
    ud, inv = np.unique(dates[sg], return_inverse=True)
    hc, nc = np.bincount(inv, weights=hit.astype(float)), np.bincount(inv)
    bi = rng.integers(0, len(ud), (B, len(ud))); bp = hc[bi].sum(1) / nc[bi].sum(1)
    out.update(hits=k, precision=k / m, wilson_lo=lo, wilson_hi=hi, day_ci_lo=float(np.quantile(bp, .025)),
               day_ci_hi=float(np.quantile(bp, .975)), days_with_signals=int(len(ud)),
               precision_opt=float(pick(lab["up_o"], lab["dn_o"], sg, dd).mean()),
               ambiguous_signals=int(pick(lab["up_amb"], lab["dn_amb"], sg, dd).sum()))
    P = np.argsort(rng.random((B, m)), axis=1)                       # B1: same bars, directions permuted (count-preserving)
    b1 = np.where(dd[P] > 0, up[sg][None], dn[sg][None]).mean(1)
    rpos = np.where(mask)[0]; N = len(rpos); p = np.searchsorted(rpos, sg)   # B2: same signal series, wall-row shifted in period
    i2 = rpos[(p[None] + rng.integers(1, N, B)[:, None]) % N]; v2 = scor[i2]
    b2 = (np.where(dd[None] > 0, up[i2], dn[i2]) & v2).sum(1) / np.maximum(v2.sum(1), 1)
    out.update(dir_perm_mean=float(b1.mean()), p_dir=float((1 + (b1 >= k / m).sum()) / (B + 1)),
               shift_mean=float(b2.mean()), p_time=float((1 + (b2 >= k / m).sum()) / (B + 1)))
    ev_tot = ev_det = 0; late, kto = [], []
    for side, arr, kk in ((1, up, lab["up_k"]), (-1, dn, lab["dn_k"])):
        s_ = arr & mask; stt = s_ & ~np.r_[False, s_[:-1]]
        rid = np.cumsum(stt) * s_; starts = np.where(stt)[0]; ev_tot += len(starts)
        g = sg[dd == side]; ids = rid[g]; first = {}
        for t, i in zip(g[ids > 0], ids[ids > 0]): first[i] = min(first.get(i, 10 ** 9), t)
        ev_det += len(first); late += [first[i] - starts[i - 1] for i in first]; kto += [kk[t] for t in g[ids > 0]]
    out.update(events=ev_tot, events_detected=ev_det, recall=ev_det / ev_tot if ev_tot else np.nan,
               median_lateness=float(np.median(late)) if late else np.nan, mean_bars_to_target=float(np.nanmean(kto)) if kto else np.nan)
    return out


def holm(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i]); run, adj = 0.0, [None] * len(pvals)
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(pvals) - r) * pvals[i])); adj[i] = run
    return adj


def jdump(o, path):
    with open(path, "w") as f: json.dump(o, f, indent=2, default=lambda x: x.item() if hasattr(x, "item") else str(x))


# ------------------------------------------------------------------ stage 1
def pooled_frame(sym, d, lab, sets, mask):
    rows = []
    for m in MODELS18:
        idx, dr = sets[(m, "cd10")]; k = mask[idx]; idx, dr = idx[k], dr[k]
        k = lab["status"][idx] == 0; idx, dr = idx[k], dr[k]
        nm = np.where(dr > 0, 1, 0)
        hit = np.where(dr > 0, lab["up_c"][idx], lab["dn_c"][idx])
        f = pd.DataFrame(sig_features(d, idx, dr)); f["model"], f["hit"], f["idx"], f["dr"] = m, hit, idx, dr
        f["day"] = d.ts.dt.floor("D").values.astype("datetime64[D]")[idx]; f["outcome"] = outcome_class(d, lab, idx, dr)
        f["range_atr"] = (d.high.values[idx] - d.low.values[idx]) / d.atr.values[idx]
        rows.append(f)
    return pd.concat(rows, ignore_index=True)


def stage1(a):
    out = Path(a.out) / "stage1"; out.mkdir(parents=True, exist_ok=True)
    report, cand_stats = {}, {}
    pools = {}
    for sym in ("ES", "NQ"):
        d, labs, sig, wl = prep(sym, a.data_dir, a.exports); lab = labs["close"]; sets = signal_sets(d, sig, wl)
        mask = periods(d, sym)["train"]; dates = d.ts.dt.floor("D").values.astype("datetime64[D]")
        rows = []
        for (m, v), (idx, dr) in sets.items():
            if v in ("cd10", "as_exported"):
                r = score_set(idx, dr, lab, dates, mask, f"{sym}|{m}|{v}|train|close"); r.update(symbol=sym, model=m, variant=v); rows.append(r)
        pd.DataFrame(rows).to_csv(out / f"{sym}_train_models.csv", index=False)
        pf = pooled_frame(sym, d, lab, sets, mask); pools[sym] = pf
        oc = pf.groupby("outcome").size().to_dict(); report[sym] = dict(pooled_signals=len(pf), outcome_counts=oc,
                                                                      pooled_precision=float(pf.hit.mean()))
        report[sym]["range_atr_mean_success_vs_fail"] = [float(pf[pf.hit].range_atr.mean()), float(pf[~pf.hit].range_atr.mean())]
        cs = {}
        for c in CANDS:
            T, F = pf[pf[c]], pf[~pf[c]]
            rng = np.random.default_rng(zlib.crc32(f"{sym}{c}".encode()))
            g = pf.groupby(["day", pf[c].astype(int)]).hit.agg(["sum", "count"]).unstack(fill_value=0)
            sm, ct = g["sum"].reindex(columns=[0, 1], fill_value=0), g["count"].reindex(columns=[0, 1], fill_value=0)
            D = len(sm); bi = rng.integers(0, D, (2000, D))
            tn_, fn_ = ct[1].values[bi].sum(1), ct[0].values[bi].sum(1)
            diffs = (sm[1].values[bi].sum(1) / np.maximum(tn_, 1) - sm[0].values[bi].sum(1) / np.maximum(fn_, 1))[(tn_ > 0) & (fn_ > 0)]
            cons = 0; tot = 0
            for m_, g in pf.groupby("model"):
                gt, gf = g[g[c]], g[~g[c]]
                if len(gt) >= 20 and len(gf) >= 20: tot += 1; cons += gt.hit.mean() > gf.hit.mean()
            cs[c] = dict(n_true=len(T), n_false=len(F), prec_true=float(T.hit.mean()), prec_false=float(F.hit.mean()),
                         diff=float(T.hit.mean() - F.hit.mean()), day_ci_diff=[float(np.quantile(diffs, .025)), float(np.quantile(diffs, .975))],
                         models_positive=f"{cons}/{tot}")
        cand_stats[sym] = cs
    elig = {}
    for c in CANDS:
        e, n = cand_stats["ES"][c], cand_stats["NQ"][c]
        if e["diff"] > 0 and n["diff"] > 0 and min(e["n_true"], e["n_false"], n["n_true"], n["n_false"]) >= 200:
            elig[c] = min(e["diff"], n["diff"])
    chosen = max(elig, key=elig.get) if elig else None
    lock = dict(status="EXPLORATORY_TRAIN_ONLY_HYPOTHESIS", train_period="2026-09-21..2026-10-05 (purged 5 bars)",
                test_period="2026-10-06..2026-10-18", candidates_declared=list(CANDS), n_candidates=len(CANDS),
                selection_rule="max over candidates of min(diff_ES, diff_NQ), requiring both diffs>0 and every group >=200 pooled signals; "
                               "diff = pooled conservative precision(feature true) - (feature false) over the 18 models' cd10 signals",
                candidate_stats=cand_stats, train_failure_analysis=report, chosen=chosen,
                chosen_definition=CANDS[chosen][0] if chosen else None, chosen_mechanism=CANDS[chosen][1] if chosen else None,
                frozen_test_protocol=dict(
                    signals="18 models' cooldown_10m_selected signals (post-filter subset: keep a signal only if the chosen feature is true)",
                    instruments="ES and NQ separately, test period only; SPX not used",
                    primary_entry="close", robustness_entry="next_open (not part of the decision)",
                    primary_test="pooled conservative precision filtered vs unfiltered; one-sided random-thinning p (same count drawn from unfiltered pool, 5000 draws); "
                                 "Bonferroni alpha 0.025 over {ES,NQ}; hypothesis supported only if BOTH instruments improve and both p<0.025",
                    also_report="recall, median lateness, signals per 1000 bars, events lost; no re-tuning of thresholds after stage 1"))
    p = out / "HYPOTHESIS_LOCKED.json"; jdump(lock, p)
    (out / "HYPOTHESIS_LOCKED.sha256").write_text(hashlib.sha256(p.read_bytes()).hexdigest())
    print(json.dumps(dict(train_failure_analysis=report, candidate_stats=cand_stats, eligible=elig, chosen=chosen), indent=1, default=str))


# ------------------------------------------------------------------ stage 2
def stage2(a):
    s1 = Path(a.out) / "stage1"; p = s1 / "HYPOTHESIS_LOCKED.json"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == (s1 / "HYPOTHESIS_LOCKED.sha256").read_text().strip(), "lock file altered"
    lock = json.load(open(p)); chosen = lock["chosen"]
    out = Path(a.out) / "stage2"; out.mkdir(parents=True, exist_ok=True)
    allrows, hyp = [], {}
    for sym in ("SPX", "ES", "NQ"):
        d, labs, sig, wl = prep(sym, a.data_dir, a.exports); sets = signal_sets(d, sig, wl)
        dates = d.ts.dt.floor("D").values.astype("datetime64[D]"); P = periods(d, sym)
        for entry, lab in labs.items():
            for per, mask in P.items():
                for (m, v), (idx, dr) in sets.items():
                    r = score_set(idx, dr, lab, dates, mask, f"{sym}|{m}|{v}|{per}|{entry}")
                    r.update(symbol=sym, model=m, variant=v, period=per, entry=entry); allrows.append(r)
        if sym != "SPX" and chosen:
            for entry, lab in labs.items():
                mask = P["test"]; rows = []; pool_b, pool_a = [], []
                for m in MODELS18:
                    idx, dr = sets[(m, "cd10")]; f = sig_features(d, idx, dr)[chosen]
                    rb = score_set(idx, dr, lab, dates, mask, f"H|{sym}|{m}|before|{entry}")
                    ra = score_set(idx[f], dr[f], lab, dates, mask, f"H|{sym}|{m}|after|{entry}")
                    rows.append(dict(model=m, **{k + "_before": v for k, v in rb.items() if k in ("n_scored", "precision", "recall", "median_lateness", "events_detected", "events", "signals_per_1000_bars")},
                                     **{k + "_after": v for k, v in ra.items() if k in ("n_scored", "precision", "recall", "median_lateness", "events_detected", "signals_per_1000_bars")}))
                    for tag, (ii, dd_), pool in (("b", (idx, dr), pool_b), ("a", (idx[f], dr[f]), pool_a)):
                        k = mask[ii] & (lab["status"][ii] == 0); ii, dd_ = ii[k], dd_[k]
                        pool.append(pd.DataFrame(dict(model=m, idx=ii, hit=np.where(dd_ > 0, lab["up_c"][ii], lab["dn_c"][ii]),
                                                      opt=np.where(dd_ > 0, lab["up_o"][ii], lab["dn_o"][ii]), day=dates[ii])))
                B_, A_ = pd.concat(pool_b), pd.concat(pool_a); rng = np.random.default_rng(zlib.crc32(f"thin{sym}{entry}".encode()))
                hb = B_.hit.values; na = len(A_); pa = A_.hit.mean()
                thin = np.array([hb[rng.choice(len(hb), na, replace=False)].mean() for _ in range(5000)])
                days = np.unique(B_.day); dd_ = []
                gb = {k: g for k, g in B_.groupby("day")}; ga = {k: g for k, g in A_.groupby("day")}
                for _ in range(2000):
                    sel = days[rng.choice(len(days), len(days))]
                    bh = sum(gb[x].hit.sum() for x in sel); bn = sum(len(gb[x]) for x in sel)
                    ah = sum(ga[x].hit.sum() for x in sel if x in ga); an = sum(len(ga[x]) for x in sel if x in ga)
                    if an: dd_.append(ah / an - bh / bn)
                tab = pd.DataFrame(rows); tab.to_csv(out / f"hypothesis_{sym}_{entry}_per_model.csv", index=False)
                hyp[f"{sym}_{entry}"] = dict(n_before=len(B_), prec_before=float(B_.hit.mean()), prec_before_opt=float(B_.opt.mean()),
                                             n_after=na, prec_after=float(pa), prec_after_opt=float(A_.opt.mean()),
                                             thinning_mean=float(thin.mean()), p_thinning=float((1 + (thin >= pa).sum()) / 5001),
                                             day_ci_diff=[float(np.quantile(dd_, .025)), float(np.quantile(dd_, .975))],
                                             macro_recall_before=float(np.nanmean(tab.recall_before)), macro_recall_after=float(np.nanmean(tab.recall_after)),
                                             events_detected_before=int(tab.events_detected_before.sum()), events_detected_after=int(tab.events_detected_after.sum()),
                                             events_total=int(tab.events_before.sum()),
                                             median_lateness_before=float(np.nanmedian(tab.median_lateness_before)), median_lateness_after=float(np.nanmedian(tab.median_lateness_after)),
                                             signals_per_1000_before=float(tab.signals_per_1000_bars_before.mean()), signals_per_1000_after=float(tab.signals_per_1000_bars_after.mean()))
    T = pd.DataFrame(allrows); T.to_csv(out / "models_all.csv", index=False)
    fam = T[(T.symbol.isin(["ES", "NQ"])) & (T.period == "full") & (T.entry == "close") & (T.variant.isin(["cd10"])) & T.p_dir.notna()]
    fam = fam.assign(p_dir_holm=holm(fam.p_dir.tolist()), p_time_holm=holm(fam.p_time.tolist()))
    fam.to_csv(out / "holm_family_ES_NQ_full_cd10_close.csv", index=False)
    jdump(dict(hypothesis=hyp, chosen=chosen, holm_family_size=len(fam)), out / "hypothesis_test.json")
    jdump(dict(models=19, instruments=3, variants={"18 models": ["raw", "cd10", "cd5"], "v4_watch": ["as_exported", "cd10"]},
               entries=2, periods={"ES/NQ": ["train", "test", "full"], "SPX": ["full"]}, hypothesis_candidates=len(CANDS),
               holm_families=dict(direction=len(fam), timing=len(fam)), hypothesis_alpha="0.025 (2 instruments)"), out / "attempts.json")
    print("done", len(T), "rows; family", len(fam))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("stage", choices=["stage1", "stage2"])
    ap.add_argument("--data-dir", default="data"); ap.add_argument("--exports", default="exports"); ap.add_argument("--out", default="results_prev")
    a = ap.parse_args(); {"stage1": stage1, "stage2": stage2}[a.stage](a)
