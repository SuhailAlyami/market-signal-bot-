"""Evaluate frozen timing model directions against stronger same-time controls."""
import json,io,zipfile,sys
from pathlib import Path
import pandas as pd,numpy as np
import exchange_calendars as xc
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent
z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
keep=np.zeros(len(d),bool)
for _,r in xc.get_calendar('XNYS').schedule.loc['2026-10-15':'2026-10-30'].iterrows():keep|=((d.ts>=r.open)&(d.ts<r.close)).values
d=ev.add_atr(ev.add_structure(d.loc[keep].reset_index(drop=True)),'prior20')
s=pd.read_csv(P/'signals_derived.csv');s['ts']=pd.to_datetime(s.decision_time_Riyadh,utc=True)-pd.Timedelta(minutes=1)
lookup={t:i for i,t in enumerate(d.ts)};ids=np.array([lookup[t] for t in s.ts]);side=s.direction.values;mom=np.sign(d.close-d.groupby('seg').close.shift(5)).values
rows=[]
for entry in ['close','next_open']:
 lab=ev.label(d,entry);ok=lab['status'][ids]==0;ix=ids[ok];dr=side[ok];day=d.ts.iloc[ix].dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d').values
 up,dn=lab['up_c'][ix],lab['dn_c'][ix];hits=np.where(dr>0,up,dn);m=mom[ix];mh=np.where(m>0,up,dn);mvalid=m!=0
 rng=np.random.default_rng(20261102);null=[];daily=[];groups=[np.flatnonzero(day==date) for date in sorted(set(day))]
 for g in groups:
  p=(dr[g]>0).mean();daily.append({'date':str(day[g[0]]),'n':len(g),'model_hits':int(hits[g].sum()),'momentum_hits':int(mh[g].sum()),'long_count':int((dr[g]>0).sum()),'same_day_null_expected_hits':float((p*up[g]+(1-p)*dn[g]).sum()),'directions_agree':int((dr[g]==m[g]).sum())})
 for _ in range(20000):
  perm=dr.copy()
  for g in groups:perm[g]=rng.permutation(dr[g])
  null.append(int(np.where(perm>0,up,dn).sum()))
 diffs=[]
 for _ in range(20000):
  sample=[daily[j] for j in rng.integers(0,len(daily),len(daily))];diffs.append(sum(x['model_hits']-x['momentum_hits'] for x in sample)/sum(x['n'] for x in sample))
 rows.append({'entry':entry,'n':len(ix),'model_hits':int(hits.sum()),'model_precision':float(hits.mean()),'momentum_hits':int(mh[mvalid].sum()),'momentum_n':int(mvalid.sum()),'momentum_precision':float(mh[mvalid].mean()),'direction_agreement_n':int((dr==m).sum()),'daily_preserving_permutation_mean':float(np.mean(null)/len(ix)),'daily_preserving_permutation_p_exploratory':float((1+sum(v>=hits.sum() for v in null))/20001),'daily_bootstrap_model_minus_momentum_95':np.quantile(diffs,[.025,.975]).tolist(),'daily':daily})
(P/'results.json').write_text(json.dumps({'rule_changed':False,'signals_changed':False,'rows':rows,'limitations':'posthoc robustness audit; five days; consumed data; no correction for entire prior research family'},indent=2));print(json.dumps(rows,indent=2))
