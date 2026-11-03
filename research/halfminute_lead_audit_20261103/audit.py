"""Fixed descriptive 30-second alignment/lead audit. No trading signal."""
import json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
P=Path(__file__).resolve().parent

def load(path):
 x=json.loads(Path(path).read_text());keys=['open','high','low','close'];d=pd.DataFrame({'ts':pd.to_datetime(x['time'],utc=True),**{k:x[k] for k in keys}})
 if d.ts.duplicated().any() or not d.ts.is_monotonic_increasing:raise ValueError('duplicate/unordered timestamp')
 if not d.ts.dt.second.isin([0,30]).all() or (d.ts.dt.microsecond!=0).any():raise ValueError('not30second-aligned')
 if not np.isfinite(d[keys]).all().all() or (d[keys]<=0).any().any():raise ValueError('invalid prices')
 if not ((d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))).all():raise ValueError('inconsistent OHLC')
 if 'volume' in x:d['volume']=x['volume']
 loc=d.ts.dt.tz_convert('America/New_York');mins=loc.dt.hour*60+loc.dt.minute
 return d[(mins>=570)&(mins<960)&(loc.dt.dayofweek<5)].reset_index(drop=True)

def minute_bars(d):
 d=d.copy();d['minute']=d.ts.dt.floor('min');g=d.groupby('minute');a=g.agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),count=('ts','size'));return a[a['count']==2].drop(columns='count').reset_index().rename(columns={'minute':'ts'})

def pairs(d,lag):
 # positive lag: ES return now paired with SPX return later.
 e=np.log(d.close_ES).diff();s=np.log(d.close_SPX).diff();consecutive=d.ts.diff().dt.total_seconds()==30;e=e.where(consecutive);s=s.where(consecutive);future=s.shift(-lag)
 ok=np.isfinite(e)&np.isfinite(future)
 if lag>0:
  for k in range(1,lag+1):ok&=(d.ts.shift(-k)-d.ts).dt.total_seconds()==30*k
 elif lag<0:
  for k in range(1,-lag+1):ok&=(d.ts-d.ts.shift(k)).dt.total_seconds()==30*k
 return e[ok].values,future[ok].values,ok

def main():
 p={'question':'Do same-source native30s ES returns lead SPX at30/60seconds on available Nov2 RTH sample?','lags_seconds':[-60,-30,0,30,60],'positive_lag':'ES current return vs later SPX return','primary':'descriptive correlations at every prespecified lag; no optimize-and-pick-best','direction_check':'sign ES current vs SPX next30s, compare SPX current momentum at identical nonzero times','sample':'Nov2 consumed diagnostic only; one session not independent holdout','not_a_trade_test':'no target/stop change or claimed hit-rate for original detector; no model fitting or alerts','audit':'aggregate pairs of30s bars to1min and compare native1min SPX; missing halves rejected','status':'RESEARCH_ONLY_NOT_READY'};b=json.dumps(p,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 e=load(P/'ES_raw.json');s=load(P/'SPX_raw.json');d=s.merge(e,on='ts',how='inner',suffixes=('_SPX','_ES'),validate='one_to_one');lagrows=[]
 for lag in [-2,-1,0,1,2]:
  x,y,_=pairs(d,lag);lagrows.append({'ES_lead_seconds':lag*30,'n_pairs':len(x),'return_correlation':float(np.corrcoef(x,y)[0,1])})
 x,y,ok=pairs(d,1);current=np.log(d.close_SPX).diff()[ok].values;nonzero=(x!=0)&(y!=0)&(current!=0);xx=x[nonzero];yy=y[nonzero];mm=current[nonzero];truth=np.sign(yy);agreement=np.sign(xx)==truth;momentum=np.sign(mm)==truth
 agg=minute_bars(s);native=pd.read_csv(P.parent/'nov2_final_review/SPX_20261102.csv');native['ts']=pd.to_datetime(native.pop('timestamp'),utc=True);joined=agg.merge(native,on='ts',suffixes=('_30s_agg','_1m'));delta=np.column_stack([joined[k+'_30s_agg']-joined[k+'_1m'] for k in ['open','high','low','close']])
 result={'status':'DESCRIPTIVE_RESEARCH_ONLY_NOT_READY','ES_RTH_rows':len(e),'SPX_RTH_rows':len(s),'matched_rows':len(d),'matched_dates':d.groupby(d.ts.dt.strftime('%Y-%m-%d')).size().to_dict(),'matched_gap_count':int((d.ts.diff().dt.total_seconds().iloc[1:]!=30).sum()),'lag_correlations':lagrows,'next30second_direction_diagnostic':{'n_same_nonzero_pairs':len(yy),'ES_sign_agreement':float(agreement.mean()),'SPX_momentum_agreement':float(momentum.mean()),'majority_direction_baseline_posthoc':float(max((truth==1).mean(),(truth==-1).mean())),'warning':'all returns, no selection; one consumed session; not2ATR-before1ATR accuracy or options PnL'},'SPX_1minute_reconstruction':{'matching_minutes':len(joined),'max_abs_OHLC_difference':float(np.abs(delta).max()),'all_four_prices_exact_fraction':float((delta==0).all(1).mean())}}
 (P/'RESULT.json').write_text(json.dumps(result,indent=2));d.to_csv(P/'synchronized_30s.csv',index=False);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
