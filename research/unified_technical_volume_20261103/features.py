"""Causal combined inputs and unchanged18-model adapter."""
from pathlib import Path
import sys,numpy as np,pandas as pd
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P/'source'))
from cfd_causal_reference import Bar

def patterns(d):
 bars=[Bar(int(x.ts.timestamp()*1000),x.open,x.high,x.low,x.close) for x in d.itertuples()];signals={}
 for file in ['compare_head_shoulders.py','compare_macd.py']:
  text=(P/'source'/file).read_text().split('\ndef evaluate(')[0];lines=text.splitlines();lines=[('bs=INPUT_BARS' if line.startswith('bs=[Bar(') else line) for line in lines];ns={'__file__':str(P/'source'/file),'INPUT_BARS':bars};exec(compile('\n'.join(lines),file,'exec'),ns);signals.update(ns['signals'])
 assert len(signals)==18
 return pd.DataFrame(signals,index=d.index).add_prefix('pattern_')

def technical(d,es):
 f=pd.DataFrame(index=d.index);a=d.atr;c=d.close;group=d.seg
 shift=lambda x,k=1:x.groupby(group).shift(k)
 ema=lambda x,n:x.groupby(group).transform(lambda v:v.ewm(span=n,adjust=False).mean())
 for k in [1,5,15,30]:f['return'+str(k)]=(c-shift(c,k))/a
 for n in [5,20,50]:
  m=ema(c,n);f['distance_ema'+str(n)]=(c-m)/a;f['slope_ema'+str(n)]=(m-shift(m,5))/a
 macd=ema(c,12)-ema(c,26);f['macd']=macd/a;f['macd_hist']=(macd-ema(macd,9))/a
 ch=c-shift(c);gain=ch.clip(lower=0).groupby(group).transform(lambda x:x.ewm(alpha=1/14,adjust=False).mean());loss=(-ch.clip(upper=0)).groupby(group).transform(lambda x:x.ewm(alpha=1/14,adjust=False).mean());f['rsi14']=((100-100/(1+gain/loss.replace(0,np.nan))).where(loss>0,100).where((gain+loss)>0,50)-50)/50
 rng=d.high-d.low;body=c-d.open;f['body_ATR']=body/a;f['range_ATR']=rng/a;f['body_fraction']=body/rng.replace(0,np.nan);f['upper_wick']=(d.high-d[['open','close']].max(axis=1))/a;f['lower_wick']=(d[['open','close']].min(axis=1)-d.low)/a;f['doji']=(body.abs()<=.1*rng).astype(int)
 prevopen=shift(d.open);prevclose=shift(c);f['bull_engulf']=((body>0)&(prevclose<prevopen)&(d.open<=prevclose)&(c>=prevopen)).astype(int);f['bear_engulf']=((body<0)&(prevclose>prevopen)&(d.open>=prevclose)&(c<=prevopen)).astype(int)
 for n in [10,20,60]:
  hi=d.high.groupby(group).transform(lambda x:x.shift(1).rolling(n).max());lo=d.low.groupby(group).transform(lambda x:x.shift(1).rolling(n).min());f['channel_position'+str(n)]=(c-lo)/(hi-lo).replace(0,np.nan);f['channel_width'+str(n)]=(hi-lo)/a
 path=ch.abs().groupby(group).transform(lambda x:x.rolling(15).sum());f['efficiency15']=(c-shift(c,15))/path.replace(0,np.nan)
 es=es.copy();seg=(es.ts.diff().dt.total_seconds()!=60).cumsum();v=es.volume;med=v.groupby(seg).transform(lambda x:x.shift(1).rolling(20).median());rv=v/med.replace(0,np.nan);vv=pd.DataFrame({'ts':es.ts,'log_rvol':np.log1p(rv),'log_rvol_lag1':np.log1p(rv.groupby(seg).shift(1)),'log_volume5ratio':np.log1p(v.groupby(seg).transform(lambda x:x.rolling(5).sum())/(5*v.groupby(seg).transform(lambda x:x.shift(1).rolling(20).mean())))});joined=d[['ts']].merge(vv,on='ts',how='left',validate='one_to_one');f=pd.concat([f,joined.drop(columns='ts')],axis=1)
 f.loc[d.pos<60,:]=np.nan
 return f.replace([np.inf,-np.inf],np.nan)
