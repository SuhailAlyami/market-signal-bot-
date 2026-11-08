"""Threshold-scale variant of the wave detector vs control, with random-timing baseline. Offline research only."""
import hashlib
import json
import random
import statistics
import sys
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'opening_seed'))
from failure_baseline import DRAWS, SEED, random_signals, summarize_legs  # noqa: E402
from run_seed import SPLIT, as_sessions, atr_before, load_sessions, match_legs, reference_legs, score, summarize  # noqa: E402


def detect_scaled(bars, k):
    """Identical to wave_capture.detect except R = max(5, k*ATR6)."""
    side, low, high, low_r, high_r, last_emit, out = 0, None, None, None, None, -100, []
    for i, b in enumerate(bars):
        atr = atr_before(bars, i)
        if atr is None:
            continue
        r = max(5.0, k*atr)
        if low is None:
            low = high = b.close
            low_r = high_r = r
            continue
        change = 0
        if side >= 0:
            if b.close > high:
                high, high_r = b.close, r
            if high-b.close >= high_r:
                change = -1
        if change == 0 and side <= 0:
            if b.close < low:
                low, low_r = b.close, r
            if b.close-low >= low_r:
                change = 1
        if change:
            side = change
            low = high = b.close
            low_r = high_r = r
            if i-last_emit >= 6:
                out.append({'index': i, 'decision': b.at+timedelta(minutes=5), 'side': side, 'r': r})
                last_emit = i
    return out


def main(k=0.67):
    loaded, _ = load_sessions(HERE.parent/'opening_validation_raw.json.gz')
    sessions = as_sessions(loaded)
    blocks = {'older': lambda d: d < SPLIT, 'recent': lambda d: d >= SPLIT, 'all': lambda d: True}
    data = {}
    for day, raw, step, closing, bars in sessions:
        legs = reference_legs(bars)
        data[day] = {'raw': raw, 'step': step, 'closing': closing, 'bars': bars, 'legs': legs, 'arms': {}}
        for arm, kk in (('control', 1.0), ('scaled', k)):
            sig = detect_scaled(bars, kk)
            data[day]['arms'][arm] = {'signals': sig, 'legs': match_legs(bars, sig, legs)}
    rng = random.Random(SEED)
    report = {'k': k, 'scope': 'CONSUMED 116 sessions, in-sample'}
    for name, keep in blocks.items():
        days = [d for d in data if keep(d)]
        out = {'sessions': len(days)}
        for arm in ('control', 'scaled'):
            legs = [l for d in days for l in data[d]['arms'][arm]['legs']]
            n_sig = sum(len(data[d]['arms'][arm]['signals']) for d in days)
            a = summarize_legs(legs)
            draws = []
            for _ in range(DRAWS):
                e = 0
                for d in days:
                    sg = random_signals(rng, len(data[d]['bars']), len(data[d]['arms'][arm]['signals']), 7)
                    e += summarize_legs(match_legs(data[d]['bars'], sg, data[d]['legs']))['early']
                draws.append(e)
            rows = [score(data[d]['raw'], data[d]['step'], data[d]['closing'], s, s['side'], 0)
                    for d in days for s in data[d]['arms'][arm]['signals']]
            lags = [l['lag_minutes'] for l in legs if l['matched']]
            out[arm] = {'signals': n_sig, 'legs': a['legs'], 'early': a['early'], 'matched75': a['matched'],
                        'unmatched_per_session': round((n_sig-a['matched'])/len(days), 3),
                        'median_lag_min': statistics.median(lags) if lags else None,
                        'random_early_mean': round(statistics.mean(draws), 2),
                        'early_excess_over_random': round(a['early']-statistics.mean(draws), 2),
                        'net_cost1_zero_delay': round(sum(r['gross_low']-1 for r in rows if r['status'] == 'SCORED'), 2),
                        'scored': sum(r['status'] == 'SCORED' for r in rows)}
        report[name] = out
    c, s = {g: report[g]['control'] for g in ('older', 'recent')}, {g: report[g]['scaled'] for g in ('older', 'recent')}
    checks = {g: {'early_excess_positive': s[g]['early_excess_over_random'] > 0, 'early_ge_control': s[g]['early'] >= c[g]['early'],
                  'unmatched_le_control_plus_1': s[g]['unmatched_per_session'] <= c[g]['unmatched_per_session']+1.0,
                  'matched75_ge_control': s[g]['matched75'] >= c[g]['matched75']} for g in c}
    report['checks'] = checks
    report['decision'] = 'QUALIFIES_FOR_UNUSED_SESSION_TEST_ONLY' if all(all(v.values()) for v in checks.values()) else 'REJECT_CHANGE_KEEP_CONTROL'
    report['protocol_sha256'] = hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
    json.dump(report, sys.stdout, indent=1)


if __name__ == '__main__':
    main()
