"""Causal subminute AMD sweep/reclaim; no continuation trend filter."""
from collections import Counter
import numpy as np
import pandas as pd
from intrabar_compression import minute_frame,context_frame,context_positions
from independent_strategy_models import common_risk_plan
from hunter_runtime import futures_active

VERSION='intrabar-sweep-v1'


def detect(raw,carry_sweep=False):
    minute=minute_frame(raw);contexts=context_frame(minute)
    fs=[f for _,f in contexts.iterrows()];positions=context_positions(minute,raw.index)
    medians=raw.Volume.shift(2).rolling(12).median().to_numpy()
    clocks={t:futures_active(t.to_pydatetime()) for t in sorted(set((raw.index+pd.Timedelta(seconds=5)).floor('min')))}
    rows=list(raw.itertuples(index=False,name=None));plans=[];diagnostics=Counter()
    active=None;cooldown=None;last_context=-2;side=0;extreme=None;cisd=None;confirm=0;sweep_index=-1
    swept_low=False;swept_high=False;last_start=None;frozen=None;sweep_time=None
    for i,(start,row) in enumerate(zip(raw.index,rows)):
        end=start+pd.Timedelta(seconds=5);o,h,l,c,v=row;j=int(positions[i])
        gap=last_start is not None and start-last_start!=pd.Timedelta(seconds=5);last_start=start
        if gap:
            side=0;confirm=0;swept_low=False;swept_high=False;extreme=None;cisd=None;sweep_index=-1;frozen=None;sweep_time=None
            if active:active=None;cooldown=end+pd.Timedelta(minutes=5)
        if active:
            invalid=v>0 and active['direction']*(c-active['stop_loss'])<=0
            if invalid or end-active['started']>=pd.Timedelta(minutes=10):active=None;cooldown=end+pd.Timedelta(minutes=5)
            continue
        if j<0 or not clocks[end.floor('min')] or (cooldown is not None and end<cooldown):continue
        carrying=bool(carry_sweep and side and frozen is not None and sweep_time is not None and end-sweep_time<pd.Timedelta(minutes=10))
        f=frozen if carrying else fs[j]
        if (j!=last_context and not carrying) or (carry_sweep and side and not carrying):
            if side:diagnostics['pending_sweeps_expired_or_context_reset']+=1
            last_context=j;side=0;confirm=0;extreme=None;cisd=None;sweep_index=-1;swept_low=False;swept_high=False;frozen=None;sweep_time=None
            f=fs[j]
        elif carrying and j!=last_context:diagnostics['carried_five_second_observations']+=1
        if not bool(f['valid']) or f['contraction']>.65 or not all(np.isfinite(x) for x in row) or v<=0 or l<=0 or h<max(o,c,l) or l>min(o,c):
            confirm=0;continue
        low_edge=f['low5'];high_edge=f['high5'];buffer=.1*f['atr']
        swept_low=swept_low or l<=low_edge-buffer
        swept_high=swept_high or h>=high_edge+buffer
        if swept_low and swept_high:
            side=0;confirm=0;frozen=None;sweep_time=None;diagnostics['ambiguous_context_bars']+=1;continue
        if swept_low and (side!=1 or l<extreme):
            side=1;extreme=l;cisd=o;sweep_index=i;confirm=0;diagnostics['sweep_observations']+=1
        elif swept_high and (side!=-1 or h>extreme):
            side=-1;extreme=h;cisd=o;sweep_index=i;confirm=0;diagnostics['sweep_observations']+=1
        if side and frozen is None:
            frozen=f;sweep_time=end
        if not side or i<=sweep_index:continue  # never infer ordering inside the sweep bar
        reclaimed=(c>=low_edge+buffer if side>0 else c<=high_edge-buffer) and side*(c-cisd)>0
        confirm=confirm+1 if reclaimed else 0
        if confirm<2 or side*(c-o)<=0 or i<13 or start-raw.index[i-13]!=pd.Timedelta(seconds=65):continue
        median=medians[i]
        if not np.isfinite(median) or median<=0 or (v+rows[i-1][4])/(2*median)<1.2:continue
        diagnostics['qualified_reclaims']+=1
        stop=extreme-side*.25
        plan,reason=common_risk_plan({'direction':'UP' if side>0 else 'DOWN','invalidation':stop},
            {'atr':f['atr'],'close':c})
        if plan is None:diagnostics[reason]+=1;continue
        plans.append(dict(index=j,direction=side,bar_time=start.isoformat(),detected_at=end.isoformat(),
            context_bar=minute.index[last_context].isoformat(),rule_version='intrabar-sweep-carry-v1' if carry_sweep else VERSION,**plan))
        active=dict(direction=side,stop_loss=plan['stop_loss'],started=end);confirm=0;diagnostics['complete_plans']+=1
        if carry_sweep:side=0;frozen=None;sweep_time=None
    return minute,plans,dict(diagnostics)
