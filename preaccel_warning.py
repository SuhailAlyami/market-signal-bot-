"""Research WATCH before a range breach; separate optional entry lifecycle."""
from collections import Counter
import numpy as np
import pandas as pd
from intrabar_compression import minute_frame,context_frame,context_positions
from hunter_runtime import futures_active
from independent_strategy_models import common_risk_plan

VERSION='preaccel-pressure-v1'


def detect(raw,mode='pressure'):
    if mode not in ('pressure','episode'):raise ValueError('unknown_warning_model')
    version=VERSION if mode=='pressure' else 'compression-episode-watch-v1'
    minute=minute_frame(raw);contexts=context_frame(minute)
    fs=[f for _,f in contexts.iterrows()];positions=context_positions(minute,raw.index)
    medians=raw.Volume.shift(1).rolling(12).median().to_numpy()
    rows=list(raw.itertuples(index=False,name=None));warnings=[];entries=[];pending={};seen={};diagnostics=Counter()
    clocks={t:futures_active(t.to_pydatetime()) for t in sorted(set((raw.index+pd.Timedelta(seconds=5)).floor('min')))}
    last=None;last_context=-1;compressed=False
    for i,(start,row) in enumerate(zip(raw.index,rows)):
        end=start+pd.Timedelta(seconds=5);o,h,l,c,v=row;j=int(positions[i])
        gap=last is not None and start-last!=pd.Timedelta(seconds=5);last=start
        if gap:pending.clear();seen.clear();compressed=False;last_context=-1;diagnostics['gaps']+=1
        valid=all(np.isfinite(x) for x in row) and v>0 and l>0 and h>=max(o,c,l) and l<=min(o,c)
        contiguous=i>=12 and start-raw.index[i-12]==pd.Timedelta(seconds=60)
        if not valid or not contiguous or j<0 or not clocks[end.floor('min')]:
            for state in pending.values():state['confirm']=0
            continue
        f=fs[j]
        # Entry rejection cannot put the WATCH scanner into ACTIVE or cooldown.
        for side,state in list(pending.items()):
            if side*(c-state['invalidation'])<=0 or end-state['started']>=pd.Timedelta(minutes=10):
                del pending[side];diagnostics['entry_invalidated_or_expired']+=1;continue
            beyond=side*(c-state['level'])>=.1*state['atr']
            state['confirm']=state['confirm']+1 if beyond else 0
            if state['confirm']<2:continue
            if mode=='episode' and (not np.isfinite(medians[i]) or medians[i]<=0 or v/medians[i]<1.2 or side*(c-o)<=0):continue
            plan,reason=common_risk_plan({'direction':'UP' if side>0 else 'DOWN','invalidation':state['invalidation']},
                {'close':c,'atr':f['atr']})
            del pending[side]
            if plan is None:diagnostics['entry_rejected_'+reason]+=1;continue
            entries.append(dict(index=j,direction=side,bar_time=start.isoformat(),detected_at=end.isoformat(),
                state='ENTRY_CONFIRMED',watch_id=state['watch_id'],rule_version=version,**plan))
            diagnostics['entries']+=1
        formation=False
        if mode=='episode' and j!=last_context:
            current=bool(f['valid']) and f['contraction']<=.65
            formation=current and not compressed;compressed=current;last_context=j
        if not bool(f['valid']) or f['contraction']>.65:continue
        atr=f['atr'];hi=f['high5'];lo=f['low5']
        if mode=='episode' and not lo<=c<=hi:continue
        if mode=='pressure' and 0<=hi-c<=.2*atr and 0<=c-lo<=.2*atr:continue
        up=(formation and f['trend5']>0) if mode=='episode' else (0<=hi-c<=.2*atr and lo<=c<=hi and c>o and f['trend5']>0)
        down=(formation and f['trend5']<0) if mode=='episode' else (0<=c-lo<=.2*atr and lo<=c<=hi and c<o and f['trend5']<0)
        if up==down:continue
        median=medians[i]
        if not np.isfinite(median) or median<=0 or (mode=='pressure' and v/median<1.2):continue
        side=1 if up else -1
        key=(side,int(round(lo/.25)),int(round(hi/.25)))
        if mode=='pressure' and seen.get(side)==key:diagnostics['duplicate_warning']+=1;continue
        seen[side]=key;watch_id=f'{side}:{start.isoformat()}:{key[1]}:{key[2]}'
        warnings.append(dict(index=j,direction=side,bar_time=start.isoformat(),detected_at=end.isoformat(),
            state='WATCH',watch_id=watch_id,rule_version=version,level=float(hi if side>0 else lo),
            invalidation=float(lo if side>0 else hi),price=float(c),rvol=float(v/median),
            entry_confirmed=False,notify_eligible=False,readiness='NOT_READY',source='IBKR native ESU6 historical TRADES'))
        pending[side]=dict(started=end,level=hi if side>0 else lo,invalidation=lo if side>0 else hi,
            atr=atr,confirm=0,watch_id=watch_id)
        diagnostics['warnings']+=1
    return minute,warnings,entries,dict(diagnostics)
