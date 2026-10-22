"""PDF-inspired, causal price-action observations; never a notification gate.

Source mapping and deliberately missing confirmations: docs/PDF_RULE_REVIEW.md.
OHLC is not volume at price. Nothing here infers institutions or an options price.
"""
import math

VERSION = "pdf-price-context-v1"
WINDOW = 20


def observe(bars, index):
    result = dict(version=VERSION, mode="SHADOW", notify_eligible=False,
                  readiness="NOT_READY", status="unavailable",
                  volume_profile_status="unavailable_trade_volume_at_price",
                  unverified_confirmations=["HTF_FVG_rejection", "CISD", "SMT"],
                  complete_pdf_setup=False)
    # Never inspect a later bar, including an incomplete provider update.
    if index < WINDOW + 1 or index >= len(bars):
        return {**result, "reason": "insufficient_history"}
    window = bars.iloc[index-WINDOW-1:index+1]
    try:
        times = window.index
        if times.tz is None or any((times[i]-times[i-1]).total_seconds() != 60
                                  for i in range(1, len(times))):
            return {**result, "reason": "noncontiguous_or_naive_bars"}
        rows = [tuple(float(row[k]) for k in ("Open", "High", "Low", "Close"))
                for _, row in window.iterrows()]
        if any(not all(math.isfinite(v) and v > 0 for v in r) or
               r[1] < max(r[0], r[3]) or r[2] > min(r[0], r[3]) for r in rows):
            return {**result, "reason": "invalid_ohlc"}
        o, h, l, c = rows[-1]
        prior = rows[1:-1]
        hi, lo = max(r[1] for r in prior), min(r[2] for r in prior)
        atr = sum(max(rows[j][1]-rows[j][2], abs(rows[j][1]-rows[j-1][3]),
                      abs(rows[j][2]-rows[j-1][3])) for j in range(1, WINDOW+1))/WINDOW
        if atr <= 0 or hi <= lo:
            return {**result, "reason": "flat_history"}
        # A wick alone is insufficient: the completed close must reclaim the range.
        sweep_up, sweep_down = l < lo and c > lo, h > hi and c < hi
        sweep = "AMBIGUOUS" if sweep_up and sweep_down else "UP" if sweep_up else "DOWN" if sweep_down else None
        gap = "UP" if l > rows[-3][1] else "DOWN" if h < rows[-3][2] else None
        inversions = []
        # Earlier completed three-candle gaps only; a previous close through it
        # consumes the inversion. Intrabar touches do not count as close evidence.
        for j in range(2, len(rows)-1):
            high2, low2 = rows[j-2][1:3]
            highj, lowj = rows[j][1:3]
            closes = [r[3] for r in rows[j:-1]]
            if highj < low2 and c > low2 and all(x <= low2 for x in closes):
                inversions.append((j, "UP", highj, low2))
            if lowj > high2 and c < high2 and all(x >= high2 for x in closes):
                inversions.append((j, "DOWN", high2, lowj))
        inverse = inversions[-1] if inversions else None
        return {**result, "status": "observed", "bar_start": times[-1].isoformat(),
                "prior_high": hi, "prior_low": lo, "sweep_direction": sweep,
                "swept_extreme": l if sweep == "UP" else h if sweep == "DOWN" else None,
                "opposite_liquidity_reference": hi if sweep == "UP" else lo if sweep == "DOWN" else None,
                "gap_direction": gap, "inversion_direction": inverse[1] if inverse else None,
                "inversion_zone": list(inverse[2:]) if inverse else None,
                "body_atr": abs(c-o)/atr, "range_atr": (h-l)/atr}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return {**result, "reason": "invalid_context_inputs"}
