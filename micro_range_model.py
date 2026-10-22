"""Fixed local-compression breakout hypothesis, separate from live production."""
import math
from compare_amd_reclaim import rolling_features

VERSION='micro-range-5-v1'


def features(bars):
    f=rolling_features(bars)
    f['micro_high']=bars.High.shift(1).rolling(5).max()
    f['micro_low']=bars.Low.shift(1).rolling(5).min()
    return f


def candidate(f,row,previous=None):
    if not f['valid']:return None
    atr=float(f['atr']);hi=float(f['micro_high']);lo=float(f['micro_low'])
    if not all(math.isfinite(x) for x in (atr,hi,lo,f['rvol'],f['contraction'])) or atr<=0 or hi<=lo:return None
    if f['contraction']>.65 or f['rvol']<1.2:return None
    span=float(row.High-row.Low)
    if span<=0:return None
    up=(row.Close>=hi+.1*atr and row.Close>row.Open and
        f['trend_5']>0 and f['trend_15']>=0 and (row.High-row.Close)/span<=.25)
    down=(row.Close<=lo-.1*atr and row.Close<row.Open and
          f['trend_5']<0 and f['trend_15']<=0 and (row.Close-row.Low)/span<=.25)
    side=1 if up and not down else -1 if down and not up else 0
    if not side:return None
    # Fresh structural stop from the SAME completed consolidation/break candle.
    # Never shrink a wide stop just to pass the common2ATR risk gate.
    stop=min(lo,float(row.Low))-.25 if side>0 else max(hi,float(row.High))+.25
    return dict(direction=side,price=float(row.Close),atr=atr,level=hi if side>0 else lo,
                invalidation=stop,rvol=float(f['rvol']))
