"""Streaming reference for v3 PRICE features and confirmed WATCH lifecycle.

Synthetic regression harness, not an independently verified Pine emulator.
Timestamps are minute opening times in milliseconds. Only closed bars accepted.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Bar:
    time: int
    open: float
    high: float
    low: float
    close: float

    def valid(self):
        return (all(isfinite(x) and x > 0 for x in
                    (self.open, self.high, self.low, self.close))
                and self.low <= min(self.open, self.close)
                and self.high >= max(self.open, self.close))


def directions(bars):
    """Return RANGE_READY, FAILED_BREAK; current decision uses prior features."""
    if len(bars) < 31:
        return False, 0, 0
    w = bars[-31:]
    if not all(b.valid() for b in w) or any(
            b.time-a.time != 60000 for a, b in zip(w, w[1:])):
        return False, 0, 0
    c = w[-1]
    prior = w[-21:-1]
    atr = sum(max(b.high-b.low, abs(b.high-p.close), abs(b.low-p.close))
              for p, b in zip(w[-22:-2], prior))/20
    h = max(b.high for b in w[-6:-1])
    l = min(b.low for b in w[-6:-1])
    if atr <= 0 or h <= l:
        return False, 0, 0
    width = max(b.high for b in w[-4:-1])-min(b.low for b in w[-4:-1])
    size = c.high-c.low
    inside = l <= c.close <= h
    up = (width <= 1.5*atr and size <= atr and inside and h-c.close <= .25*atr
          and c.close > c.open and c.close > w[-2].close)
    down = (width <= 1.5*atr and size <= atr and inside and c.close-l <= .25*atr
            and c.close < c.open and c.close < w[-2].close)
    fraction = (c.close-c.low)/size if size else .5
    fu = (size <= 2*atr and c.low < l and c.high <= h and inside
          and c.close > c.open and fraction >= .6)
    fd = (size <= 2*atr and c.high > h and c.low >= l and inside
          and c.close < c.open and fraction <= .4)
    return True, (1 if up and not down else -1 if down and not up else 0), (
        1 if fu and not fd else -1 if fd and not fu else 0)


class Watch:
    def __init__(self):
        self.side = 0
        self.started = self.last_decision = self.last_bar = None
        self.invalidation = None

    def step(self, bar, valid, direction, confirmed=True):
        if not confirmed:
            return None
        close_time = bar.time+60000
        terminated = False
        if self.side:
            gap = self.last_bar is not None and bar.time-self.last_bar != 60000
            expired = close_time-self.started >= 600000
            crossed = self.side*(bar.close-self.invalidation) <= 0
            if not valid or gap or expired or crossed:
                self.side = 0
                terminated = True
        cooled = self.last_decision is None or close_time-self.last_decision >= 600000
        event = 'END' if terminated else None
        if valid and not self.side and not terminated and cooled and direction:
            self.side = direction
            self.started = self.last_decision = close_time
            self.invalidation = bar.low if direction == 1 else bar.high
            event = 'UP' if direction == 1 else 'DOWN'
        self.last_bar = bar.time
        return event


def replay(bars, model=0):
    state, events, history = Watch(), [], []
    for bar in bars:
        history.append(bar)
        valid, ready, failed = directions(history)
        event = state.step(bar, valid, (ready, failed)[model])
        events.append((bar.time+60000, ready, failed, event, state.side))
    return events
