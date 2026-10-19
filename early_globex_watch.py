"""Early ES/NQ Globex watch: research only; no option orders or live-feed claims."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
BAR = timedelta(minutes=5)
MAX_AGE = timedelta(minutes=10)


def globex_active(now):
    """Regular CME equity-index futures hours; holiday exceptions require exchange calendar."""
    ny = now.astimezone(NY)
    if ny.weekday() == 5:
        return False
    if ny.weekday() == 6:
        return ny.hour >= 18
    if ny.weekday() == 4:
        return ny.hour < 17
    return ny.hour >= 18 or ny.hour < 17


def detect_early(symbol, frame, now):
    """Only completed, fresh 5m candles; prior range excludes signal candle."""
    if not globex_active(now) or not isinstance(frame.index, pd.DatetimeIndex):
        return None
    if frame.index.tz is None:
        return None
    needed = ("High", "Low", "Close", "Volume")
    if any(c not in frame for c in needed):
        return None
    data = frame.sort_index()
    data = data[data.index <= pd.Timestamp(now - BAR)]
    if len(data) < 5:
        return None
    end = data.index[-1].to_pydatetime().astimezone(UTC) + BAR
    if end > now or now - end > MAX_AGE:
        return None
    recent = data.iloc[-13:-1] if len(data) >= 14 else data.iloc[:-1]
    bar = data.iloc[-1]
    if recent[list(needed)].isna().any().any() or bar[list(needed)].isna().any():
        return None
    if (recent.Volume <= 0).any() or bar.Volume <= 0:
        return None
    # Reject gaps and synthetic zero-volume sessions.
    if any((data.index[-j] - data.index[-j-1]) != pd.Timedelta(minutes=5) for j in range(1, len(recent) + 1)):
        return None
    top, bottom = float(recent.High.max()), float(recent.Low.min())
    close = float(bar.Close)
    rvol = float(bar.Volume / recent.Volume.mean())
    direction = "WATCH_UP" if close > top else ("WATCH_DOWN" if close < bottom else None)
    if direction is None or rvol < 1.5:
        return None
    return dict(symbol=symbol, direction=direction, price=close, rvol=rvol,
                top=top, bottom=bottom, bar_end=end.isoformat(),
                source="Yahoo Finance futures proxy; potentially delayed",
                analysis_only=True, live_feed_verified=False,
                watch_type="EARLY_GLOBEX_5M")


def scan_once(now=None):
    import yfinance as yf
    now = now or datetime.now(UTC)
    if not globex_active(now):
        return []
    results = []
    for symbol in ("ES=F", "NQ=F"):
        try:
            frame = yf.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=True)
            item = detect_early(symbol, frame, now) if not frame.empty else None
            if item:
                results.append(item)
            else:
                print(f"{symbol}: no fresh qualifying 5m signal (or data unavailable)")
        except Exception as exc:
            print(f"{symbol}: fetch failed ({type(exc).__name__})")
    return results
