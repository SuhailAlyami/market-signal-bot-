"""Frozen experimental acceleration channel, independent of v3 readiness."""
from cfd_causal_reference import directions, Watch


def acceleration(bars):
    valid, _, _ = directions(bars)
    if not valid:
        return 0
    w, c = bars[-31:], bars[-1]
    atr = sum(max(b.high-b.low, abs(b.high-p.close), abs(b.low-p.close))
              for p,b in zip(w[-22:-2],w[-21:-1]))/20
    size = c.high-c.low
    if size < 1.2*atr or size <= 0 or abs(c.close-c.open)/size < .6:
        return 0
    h = max(b.high for b in w[-4:-1])
    l = min(b.low for b in w[-4:-1])
    fraction = (c.close-c.low)/size
    if fraction >= .8 and c.close > h and w[-2].close <= h and c.close > c.open:
        return 1
    if fraction <= .2 and c.close < l and w[-2].close >= l and c.close < c.open:
        return -1
    return 0


class AccelerationWatch(Watch):
    """Same expiry/invalidation; separate three-minute notification cooldown."""
    def step(self, bar, valid, direction, confirmed=True):
        if not confirmed:
            return None
        close_time = bar.time+60000
        gap = self.last_bar is not None and bar.time-self.last_bar != 60000
        crossed = self.side != 0 and self.side*(bar.close-self.invalidation) <= 0
        flip = valid and self.side != 0 and direction == -self.side and not gap and crossed
        ended = bool(self.side and (not valid or gap or crossed or close_time-self.started >= 600000))
        if ended:
            self.side = 0
        cooled = self.last_decision is None or close_time-self.last_decision >= 180000
        event = 'END' if ended else None
        if valid and direction and not self.side and (not ended or flip) and (cooled or flip):
            self.side = direction
            self.started = self.last_decision = close_time
            self.invalidation = bar.low if direction == 1 else bar.high
            event = 'UP' if direction == 1 else 'DOWN'
        self.last_bar = bar.time
        return event
