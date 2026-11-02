import json,hashlib,importlib.util
from pathlib import Path
import pandas as pd,numpy as np
from cfd_causal_reference import Bar
from cfd_acceleration_v4 import acceleration
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('ev',P/'evaluate_previous_models.py');ev=importlib.util.module_from_spec(s);s.loader.exec_module(ev)
def vix_feature(d,v,lag=0):
 v=v.copy();cont=v.ts.diff().dt.total_seconds().eq(60).rolling(5).sum().eq(5)
 v['delta5']=(v.close-v.close.shift(5)).where(cont)
 # A lagged last completed bar is declared available at its own decision time +lag min.
 v.index=v.ts+pd.Timedelta(minutes=lag);return v.delta5.reindex(pd.DatetimeIndex(d.ts)).to_numpy(float)
def cooldown(d,idx,dr):
 last=None;keep=[]
 for j,i in enumerate(idx):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:keep.append(j);last=now
 return idx[keep],dr[keep]
def main():
 config=(P/'DESIGN.json').read_bytes();assert hashlib.sha256(config).hexdigest()==(P/'DESIGN.sha256').read_text().strip();out=P/'results';out.mkdir(exist_ok=True)
 rawd,_=ev.EV.load(P/'data/SPX_1m.csv');d=ev.EV.add_atr(ev.EV.add_structure(rawd),'prior20');v=json.loads((P/'data/VIX1D_raw.json').read_text());vf=pd.DataFrame({'ts':pd.to_datetime(v['time'],utc=True),'close':v['close']});assert not vf.ts.duplicated().any()
 bs=[Bar(int(r.ts.timestamp()*1000),r.open,r.high,r.low,r.close) for r in d.itertuples()];ds=np.array([acceleration(bs[:i+1]) for i in range(len(bs))]);dates=d.ts.dt.floor('D').values.astype('datetime64[D]');results=[];audit={}
 for lag in [0,1]:
  delta=vix_feature(d,vf,lag)
  for cut in [1400,1800]:
   sub=vix_feature(d.iloc[:cut],vf[vf.ts+pd.Timedelta(minutes=lag)<=d.ts.iloc[cut-1]],lag);assert np.allclose(sub,delta[:cut],equal_nan=True)
  eligible=np.isfinite(delta);idx=np.flatnonzero((ds!=0)&eligible);dr=ds[idx];keep=-np.sign(delta[idx])==dr
  univ=eligible&(d.ts>=pd.Timestamp('2026-10-28',tz='UTC')).values
  audit[str(lag)]={'available_spx_rows':int(eligible.sum()),'raw_base':len(idx),'raw_filtered':int(keep.sum()),'prefix_checks':2}
  for name,(ii,dd) in [('baseline',cooldown(d,idx,dr)),('filtered',cooldown(d,idx[keep],dr[keep]))]:
   pd.DataFrame({'bar_index':ii,'bar_timestamp':d.ts.iloc[ii].astype(str).values,'direction':dd,'vix1d_change5':delta[ii]}).to_csv(out/(name+'_lag'+str(lag)+'_signals.csv'),index=False)
   for entry in ['close','next_open']:
    lab=ev.EV.label(d,entry);r=ev.score_set(ii,dd,lab,dates,univ,'VIX1D|'+name+'|'+str(lag)+'|'+entry);r.update(model=name,lag_minutes=lag,entry=entry);results.append(r)
 pd.DataFrame(results).to_csv(out/'comparison.csv',index=False);(out/'audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit));print(pd.DataFrame(results)[['model','lag_minutes','entry','n_scored','hits','precision','dir_perm_mean','p_dir','events_detected']].to_string(index=False))
if __name__=='__main__':main()
