"""Versioned causal rule contract shared by runtime and the Pine port.

Frozen research remains unchanged. Runtime levels use the preceding20 bars only:
partial retained sessions cannot establish yesterday's extrema consistently.
"""
from hunter_research import causal_features, candidate_signal, DEFAULT_PARAMS

VERSION = 'hunter-rolling20-v2'
WINDOW = 20
PROXIMITY = 0.20
MIN_RVOL = 1.20
CONFIRM_BARS = 2
BUFFER_ATR = 0.10
EXPIRY_MINUTES = 10
COOLDOWN_MINUTES = 5


def features(bars,index):
    value=causal_features(bars,index)
    if value is None:return None
    # A stricter, observable range target; no inferred complete prior session.
    value['level_high']=value['range_high'];value['level_low']=value['range_low']
    value['near_high']=(value['level_high']-value['close'])/value['atr']
    value['near_low']=(value['close']-value['level_low'])/value['atr']
    return value


def candidate(bars,index):
    f=features(bars,index)
    direction=candidate_signal(f,'pre_level',{**DEFAULT_PARAMS,'proximity':PROXIMITY,'rvol':MIN_RVOL})
    if not direction:return None
    return dict(direction=int(direction),price=float(f['close']),atr=float(f['atr']),
                level=float(f['level_high'] if direction>0 else f['level_low']),
                invalidation=float(f['close']-direction*f['atr']),rvol=float(f['rvol']))
