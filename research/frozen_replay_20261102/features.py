import numpy as np
import pandas as pd

def features(d):
 pc=d.groupby('seg').close.shift(1);tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
 f=pd.DataFrame(index=d.index)
 for n in [1,5,15]:f['return'+str(n)]=(d.close-d.groupby('seg').close.shift(n))/d.atr
 f['range']=(d.high-d.low)/d.atr;f['body']=(d.close-d.open)/d.atr
 f['atr_ratio']=d.atr/tr.groupby(d.seg).transform(lambda s:s.shift(1).rolling(60).mean())
 minute=d.ts.dt.tz_convert('America/New_York').dt.hour*60+d.ts.dt.tz_convert('America/New_York').dt.minute-570
 f['session_sin']=np.sin(2*np.pi*minute/390);f['session_cos']=np.cos(2*np.pi*minute/390)
 f.loc[d.pos<60,:]=np.nan
 return f.replace([np.inf,-np.inf],np.nan)
