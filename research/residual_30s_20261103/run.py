"""Fixed ES-SPX residual30s trigger with unchanged SPX1min ATR barriers."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from data_audit import load,minute_bars
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def labels(d,ids,side,entry):
 rows=[]
 for i,dr in zip(ids,side):
  if i+10>=len(d):rows.append({'i':int(i),'side':int(dr),'outcome':'UNSCORABLE_END'});continue
  if not (d.ts.iloc[i+1:i+11].diff().dt.total_seconds().iloc[1:]==30).all() or (d.ts.iloc[i+1]-d.ts.iloc[i]).total_seconds()!=30:rows.append({'i':int(i),'side':int(dr),'outcome':'UNSCORABLE_GAP'});continue
  a=float(d.atr_SPX.iloc[i]);e=float(d.close_SPX.iloc[i] if entry=='close' else d.open_SPX.iloc[i+1]);outcome='TIMEOUT'
  for k in range(1,11):
   b=d.iloc[i+k];op=dr*(b.open_SPX-e)/a
   if op>=2:outcome='TARGET';break
   if op<=-1:outcome='STOP';break
   favorable=(b.high_SPX-e)/a if dr==1 else (e-b.low_SPX)/a;adverse=(e-b.low_SPX)/a if dr==1 else (b.high_SPX-e)/a
   if favorable>=2 and adverse>=1:outcome='AMBIGUOUS';break
   if favorable>=2:outcome='TARGET';break
   if adverse>=1:outcome='STOP';break
  rows.append({'i':int(i),'side':int(dr),'outcome':outcome})
 return rows

def features(d):
 d=d.copy();seg=(d.ts.diff().dt.total_seconds()!=30).cumsum();prevSPX=d.groupby(seg).close_SPX.shift(1);prevES=d.groupby(seg).close_ES.shift(1)
 d['r_SPX']=(d.close_SPX-prevSPX)/d.atr_SPX;d['r_ES']=(d.close_ES-prevES)/d.atr_ES;d['residual']=d.r_ES-d.r_SPX;median=d.volume.groupby(seg).transform(lambda x:x.shift(1).rolling(40).median());d['rvol']=d.volume/median.where(median>0)
 d['residual_lag1']=d.residual.groupby(seg).shift(1);d['rES_lag1']=d.r_ES.groupby(seg).shift(1);d['rvol_lag1']=d.rvol.groupby(seg).shift(1)
 return d

def select(d,raw,mask):
 ids=[];side=[];last=None
 for i in np.flatnonzero(mask&(raw!=0)):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);side.append(int(raw[i]));last=now
 return np.array(ids,int),np.array(side,int)

def main():
 c={'rule':'abs(ES30s return/ESprior20_1minATR minus SPX30s return/SPXprior20_1minATR)>=.25; ES return agrees with residual sign','volume':'ES30s volume>=1.5 previous40 halfminute median','comparisons':['price residual only','price residual plus volume','residual plus volume shifted one halfminute'],'barriers':'SPX target2ATR before1ATR in5minutes=10future30s bars, opening precedence and ambiguous failure','ATR':'SMA20 true ranges from COMPLETE1minute bars strictly before decision current minute; never20halfminute ATR','warmup':'at least21minutes from RTH open and finite current/lagged features','cooldown_seconds':600,'sample':'Nov2 consumed diagnostic only, one day; no Nov3 data loaded','optimization':'one fixed .25 threshold and1.5rvol, no sweep or tuning','entry':'current halfminute close primary, next halfminute open sensitivity; no real execution assumed','status':'RESEARCH_ONLY_NOT_READY'};blob=json.dumps(c,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 es=load(P.parent/'halfminute_lead_audit/ES_raw.json');sp=load(P.parent/'halfminute_lead_audit/SPX_raw.json');d=sp.merge(es,on='ts',suffixes=('_SPX','_ES'),validate='one_to_one');assert len(d)==780
 for name,data in [('SPX',sp),('ES',es)]:
  minute=ev.add_atr(ev.add_structure(minute_bars(data)),'prior20');mapping=minute.set_index('ts').atr;d['atr_'+name]=d.ts.dt.floor('min').map(mapping)
 d=features(d);loc=d.ts.dt.tz_convert('America/New_York');minutes=loc.dt.hour*60+loc.dt.minute-570;valid=(minutes>=21)&np.isfinite(d[['atr_SPX','atr_ES','residual','residual_lag1','rvol','rvol_lag1']]).all(axis=1)
 for cut in [100,300,600]:
  short=features(d.iloc[:cut]);np.testing.assert_allclose(short[['residual','residual_lag1','rvol','rvol_lag1']],d[['residual','residual_lag1','rvol','rvol_lag1']].iloc[:cut],equal_nan=True)
 base=np.where((d.residual>=.25)&(d.r_ES>0),1,np.where((d.residual<=-.25)&(d.r_ES<0),-1,0));withvol=np.where(d.rvol>=1.5,base,0);lag=np.where((d.residual_lag1>=.25)&(d.rES_lag1>0)&(d.rvol_lag1>=1.5),1,np.where((d.residual_lag1<=-.25)&(d.rES_lag1<0)&(d.rvol_lag1>=1.5),-1,0));out=[];sig=[]
 for name,raw in [('residual_only',base),('residual_volume',withvol),('residual_volume_lag30s',lag)]:
  ids,side=select(d,raw,valid.values)
  for entry in ['close','next_open']:
   results=labels(d,ids,side,entry);scored=[r for r in results if not r['outcome'].startswith('UNSCORABLE')];counts={key:sum(r['outcome']==key for r in results) for key in ['TARGET','STOP','TIMEOUT','AMBIGUOUS','UNSCORABLE_END','UNSCORABLE_GAP']}
   out.append({'variant':name,'entry':entry,'signals':len(ids),'scored':len(scored),'hits':counts['TARGET'],'precision':counts['TARGET']/len(scored) if scored else None,'outcomes':counts})
  for i,dr in zip(ids,side):sig.append({'variant':name,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(seconds=30)).tz_convert('Asia/Riyadh')),'direction':int(dr),'residual':float(d.residual.iloc[i]),'rvol':float(d.rvol.iloc[i])})
 (P/'RESULT.json').write_text(json.dumps({'rows':out,'prefix_checks':3,'status':'NOT_READY'},indent=2));pd.DataFrame(sig).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(out,indent=2))
if __name__=='__main__':main()
