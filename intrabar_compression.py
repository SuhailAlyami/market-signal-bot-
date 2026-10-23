"""Closed5second confirmation of immutable completed-minute compression context.

Research only until fixed independent acceptance; never called by live reader.
"""
from collections import Counter
import numpy as np
import pandas as pd
from hunter_runtime import futures_active
from independent_strategy_models import common_risk_plan

VERSION='intrabar-compression-v1'


def minute_frame(raw):
    if not isinstance(raw.index,pd.DatetimeIndex) or raw.index.tz is None or not raw.index.is_unique or not raw.index.is_monotonic_increasing:
        raise ValueError('unique_increasing_aware_5second_timestamps_required')
    if any(raw.index.microsecond) or any(raw.index.second%5):raise ValueError('unaligned_5second_timestamps')
    good=(np.isfinite(raw).all(axis=1)&raw.Low.gt(0)&raw.Volume.ge(0)&
        raw.High.ge(raw[['Open','Close','Low']].max(axis=1))&raw.Low.le(raw[['Open','Close']].min(axis=1)))
    group=raw.index.floor('min')
    minute=raw.groupby(group).agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'})
    counts=raw.groupby(group).size();quality=good.groupby(group).all()
    aligned=raw.index.second%5==0
    alignment=pd.Series(aligned,index=raw.index).groupby(group).all()
    complete=counts.eq(12)&quality&alignment
    # Fail closed, never create/fill a missing five-second observation.
    minute.loc[~complete,:]=np.nan
    return minute


def context_frame(minute):
    prev=minute.Close.shift(1)
    tr=pd.concat([minute.High-minute.Low,(minute.High-prev).abs(),(minute.Low-prev).abs()],axis=1).max(axis=1)
    f=pd.DataFrame(index=minute.index)
    f['atr']=tr.rolling(20).mean();f['high5']=minute.High.rolling(5).max();f['low5']=minute.Low.rolling(5).min()
    span20=minute.High.rolling(20).max()-minute.Low.rolling(20).min()
    f['contraction']=(f.high5-f.low5)/span20
    f['trend5']=(minute.Close-minute.Close.shift(5))/f.atr
    f['trend15']=(minute.Close-minute.Close.shift(15))/f.atr
    f['open']=minute.Open;f['close']=minute.Close;f['high']=minute.High;f['low']=minute.Low
    good=np.isfinite(minute).all(axis=1)&minute.Volume.gt(0)
    contiguous=minute.index.to_series().diff().eq(pd.Timedelta(minutes=1))
    f['valid']=good.rolling(31).sum().eq(31)&contiguous.rolling(30).sum().eq(30)&f.atr.gt(0)&span20.gt(0)
    return f


def context_positions(minute,raw_index):
    # Use at BAR START, not its closing boundary, to avoid same-bar lookahead.
    known=(minute.index+pd.Timedelta(minutes=1)).asi8
    return np.searchsorted(known,raw_index.asi8,side='right')-1


def detect(raw):
    minute=minute_frame(raw);context=context_frame(minute)
    ctxrows=[row for _,row in context.iterrows()]
    positions=context_positions(minute,raw.index)
    median_before_pair=raw.Volume.shift(2).rolling(12).median().to_numpy()
    minute_clocks=sorted(set((raw.index+pd.Timedelta(seconds=5)).floor('min')))
    active_clock={t:futures_active(t.to_pydatetime()) for t in minute_clocks}
    plans=[];diagnostics=Counter();active=None;cooldown=None;last_context=-2;side=0;confirm=0;last_time=None
    rawrows=list(raw.itertuples(index=False,name=None))
    for i,(start,r) in enumerate(zip(raw.index,rawrows)):
        end=start+pd.Timedelta(seconds=5);o,h,l,c,v=r;j=int(positions[i])
        contiguous=last_time is None or start-last_time==pd.Timedelta(seconds=5)
        last_time=start
        if not contiguous:
            confirm=0
            if active:active=None;cooldown=end+pd.Timedelta(minutes=5)
        if active:
            invalid=v>0 and active['direction']*(c-active['stop_loss'])<=0
            if invalid or end-active['started']>=pd.Timedelta(minutes=10):
                active=None;cooldown=end+pd.Timedelta(minutes=5)
            continue
        if not active_clock[end.floor('min')] or j<0 or (cooldown is not None and end<cooldown):continue
        f=ctxrows[j]
        if j!=last_context:
            last_context=j;confirm=0;side=0
            span=f['high']-f['low']
            if bool(f['valid']) and f['contraction']<=.65 and span>0:
                up=f['close']>f['open'] and 0<=f['high5']-f['close']<=.2*f['atr'] and f['trend5']>0 and f['trend15']>=0 and (f['high']-f['close'])/span<=.25
                down=f['close']<f['open'] and 0<=f['close']-f['low5']<=.2*f['atr'] and f['trend5']<0 and f['trend15']<=0 and (f['close']-f['low'])/span<=.25
                side=1 if up else -1 if down else 0
                if side:diagnostics['pressure_contexts']+=1
        if not side or not all(np.isfinite(x) for x in r) or v<=0 or l<=0 or h<max(o,c,l) or l>min(o,c):
            confirm=0;continue
        level=f['high5'] if side>0 else f['low5']
        beyond=side*(c-level)>=.1*f['atr']
        confirm=confirm+1 if beyond else 0
        if confirm<2 or i<13 or side*(c-o)<=0:continue
        if start-raw.index[i-13]!=pd.Timedelta(seconds=65):continue
        median=median_before_pair[i]
        if not np.isfinite(median) or median<=0 or (v+rawrows[i-1][4])/(2*median)<1.2:continue
        diagnostics['qualified_pairs']+=1
        stop=min(f['low'],level-.1*f['atr'])-.25 if side>0 else max(f['high'],level+.1*f['atr'])+.25
        plan,reason=common_risk_plan({'direction':'UP' if side>0 else 'DOWN','invalidation':stop},
            {'atr':f['atr'],'close':c})
        if plan is None:diagnostics[reason]+=1;continue
        plans.append(dict(index=j,direction=side,bar_time=start.isoformat(),detected_at=end.isoformat(),
            context_bar=minute.index[j].isoformat(),rule_version=VERSION,**plan))
        active=dict(direction=side,stop_loss=plan['stop_loss'],started=end)
        diagnostics['complete_plans']+=1;confirm=0
    return minute,plans,dict(diagnostics)


def refine_events(events,minute,raw):
    refined=[]
    for original in events:
        event=dict(original);a=event['anchor_index'];side=event['direction']
        anchor=float(minute.Close.iloc[a]);begin=minute.index[a]+pd.Timedelta(minutes=1)
        end=minute.index[event['end_index']]+pd.Timedelta(minutes=1)
        future=raw[(raw.index>=begin)&(raw.index<end)&raw.Volume.gt(0)]
        target=anchor+side*event['target_points'];onset=anchor+side*.25*event['target_points']
        targets=future.High.ge(target) if side>0 else future.Low.le(target)
        starts=future.High.ge(onset) if side>0 else future.Low.le(onset)
        if not targets.any() or not starts.any():continue
        event['coarse_onset_time']=event['onset_time'];event['coarse_target_time']=event['target_time']
        event['onset_time']=future.index[starts][0].isoformat()
        event['fine_target_time']=future.index[targets][0].isoformat()
        event['onset_timing']='conservative_start_of_first_positive_volume_5second_touch'
        refined.append(event)
    return refined
