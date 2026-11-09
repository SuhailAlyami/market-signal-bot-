"""Posthoc timing audit; does not modify trigger or infer sub-minute leadership."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
from run import inputs,accel,readzip,select
P=Path(__file__).resolve().parent
sp=readzip(sys.argv[1],'SPX_1min_sample.csv');es=readzip(sys.argv[2],'ES_1min_sample.csv');d,s,v=inputs(sp,es);b=accel(es);seg=(es.ts.diff().dt.total_seconds()!=60).cumsum();r=es.volume/es.volume.groupby(seg).transform(lambda x:x.shift(1).rolling(20).median());ix=np.flatnonzero((b!=0)&(r>=1.5)&v);cut=pd.Timestamp('2026-10-26',tz='UTC');out=[]
for period,mask in [('development',(d.ts<cut).values),('later_consumed',(d.ts>=cut).values)]:
 now=ix[mask[ix]];lagids=select(d,s['ES_lead_lag1'],v&mask);already=sum(s['SPX_ACCEl_baseline'][i-1]==s['ES_lead_lag1'][i] for i in lagids)
 out.append({'period':period,'ES_impulses_with_rvol':len(now),'same_minute_SPX_matching_ACCEL':int((s['SPX_ACCEl_baseline'][now]==b[now]).sum()),'same_minute_SPX_no_ACCEL':int((s['SPX_ACCEl_baseline'][now]==0).sum()),'lag_accepted_signals':len(lagids),'lag_signals_with_SPX_ALREADY_matching_previous_minute':int(already),'warning':'one-minute coincidence does not establish sub-minute leadership; lagged confirmation is not early if SPX already fired'})
(P/'TIMING_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
