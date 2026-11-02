import importlib.util,json,hashlib,math
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('ev',P/'evaluate_previous_models.py');ev=importlib.util.module_from_spec(s);s.loader.exec_module(ev)
def option_side(cp,cn,pp,pn,volumes,contiguous):
 if not contiguous or not all(math.isfinite(float(x)) and x>0 for x in [cp,cn,pp,pn,*volumes]):return 0
 return 1 if cn>cp and pn<pp else -1 if cn<cp and pn>pp else 0

def generate(j):
 ds=np.zeros(len(j),int)
 for i in range(1,len(j)):
  a,b=j.iloc[i-1],j.iloc[i];ds[i]=option_side(a.close_call,b.close_call,a.close_put,b.close_put,[a.volume_call,b.volume_call,a.volume_put,b.volume_put],(b.timestamp-a.timestamp).total_seconds()==60)
 out=[];last=None
 for i in np.flatnonzero(ds):
  t=j.timestamp.iloc[i].timestamp()
  if last is None or t-last>=600:out.append(i);last=t
 return ds,np.array(out,int)

def main():
 r=(P/'DESIGN.json').read_bytes();assert hashlib.sha256(r).hexdigest()==(P/'DESIGN.sha256').read_text().strip();out=P/'results';out.mkdir(exist_ok=True)
 j=pd.read_csv(P/'data/synchronized.csv');j.timestamp=pd.to_datetime(j.timestamp,utc=True);rawd,_=ev.EV.load(P/'data/SPX_1m.csv');d=ev.EV.add_atr(ev.EV.add_structure(rawd),'prior20')
 sides,sel=generate(j)
 for cut in [100,200,300]:
  p,ii=generate(j.iloc[:cut]);assert np.array_equal(p,sides[:cut]);assert np.array_equal(ii,sel[sel<cut])
 lookup=pd.Series(d.index.values,index=d.ts);idx=lookup.reindex(pd.DatetimeIndex(j.timestamp.iloc[sel])).to_numpy(int);dr=sides[sel]
 momentum=np.sign(d.close.values[idx]-d.close.shift(5).values[idx]).astype(int);mk=momentum!=0
 dates=d.ts.dt.floor('D').values.astype('datetime64[D]');mask=d.ts.dt.date.eq(pd.Timestamp('2026-10-30').date()).values;rows=[]
 for entry in ['close','next_open']:
  lab=ev.EV.label(d,entry)
  for model,ii,dd in [('option_direction',idx,dr),('same_times_underlying_momentum',idx[mk],momentum[mk])]:
   z=ev.score_set(ii,dd,lab,dates,mask,'OPTIONS_DIRECTION|'+model+'|'+entry);z.update(entry=entry,model=model);rows.append(z)
 pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False)
 pd.DataFrame({'bar_index':idx,'bar_timestamp':d.ts.iloc[idx].astype(str).values,'direction':dr,'underlying_5m_direction':momentum}).to_csv(out/'signals.csv',index=False)
 audit={'raw_candidate_count':int((sides!=0).sum()),'accepted_count':len(sel),'flat_underlying_baseline':int((~mk).sum()),'same_direction_as_underlying':int((dr[mk]==momentum[mk]).sum()),'direction_comparable':int(mk.sum()),'prefix_checks_passed':3,'days':1,'no_new_parameter_search':True}
 (out/'audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit));print(pd.DataFrame(rows)[['model','entry','n_scored','hits','precision','dir_perm_mean','p_dir','events_detected']].to_string(index=False))
if __name__=='__main__':main()
