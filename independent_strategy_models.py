"""Independent model contracts: strategy-specific confirmation, common risk only.

Not imported by the live reader. Quote freshness and delivery dedupe remain in
the existing adapters/senders, never implemented as exceptions inside a model.
"""
import math
from compare_amd_reclaim import amd_candidate
from strategy_rules import MIN_RVOL


def continuation_confirmation(f, side):
    return (f['rvol']>=MIN_RVOL and side*f['trend_5']>0 and
            side*f['trend_15']>=0 and side*f['move']>0)


def reversal_candidate(f,row,previous):
    candidate=amd_candidate(f,row)
    if not candidate:return None
    side=candidate['direction']
    # Explicit closed-candle delivery shift; no trend-persistence test on reversal.
    if side*(previous.Close-previous.Open)>=0 or side*(row.Close-previous.Open)<=0:return None
    return candidate


def common_risk_plan(event,f,tick=0.25):
    try:
        side=1 if event['direction']=='UP' else -1 if event['direction']=='DOWN' else 0
        price=float(f['close']);atr=float(f['atr']);stop=float(event['invalidation'])
        if not side or not all(math.isfinite(x) and x>0 for x in (price,atr,stop,tick)):
            return None,'invalid_risk_inputs'
        low=math.floor((price-.05*atr)/tick)*tick
        high=math.ceil((price+.05*atr)/tick)*tick
        stop=(math.floor(stop/tick) if side>0 else math.ceil(stop/tick))*tick
        risk=high-stop if side>0 else stop-low
        if not tick<=risk<=2*atr or not (stop<low if side>0 else stop>high):
            return None,'risk_or_entry_invalid'
        anchor=high if side>0 else low
        targets=[anchor+side*risk,anchor+side*2*risk]
        if min(targets)<=0:return None,'nonpositive_target'
        return dict(entry_zone=[low,high],stop_loss=stop,targets=targets,plan_atr=atr),None
    except (KeyError,ValueError,TypeError,OverflowError):return None,'invalid_risk_inputs'
