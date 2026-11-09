import io,zipfile
import numpy as np,pandas as pd

def readzip(path,name):
 d=pd.read_csv(io.BytesIO(zipfile.ZipFile(path).read(name)));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
 if d.ts.duplicated().any() or not d.ts.is_monotonic_increasing:raise ValueError('timestamp integrity')
 for col in ['open','high','low','close']:
  if not np.isfinite(d[col]).all() or (d[col]<=0).any():raise ValueError('price validity')
 if not ((d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))).all():raise ValueError('OHLC integrity')
 if 'volume' in d and (not np.isfinite(d.volume).all() or (d.volume<=0).any()):raise ValueError('volume integrity')
 loc=d.ts.dt.tz_convert('America/New_York');mins=loc.dt.hour*60+loc.dt.minute
 return d[(mins>=570)&(mins<960)&(loc.dt.dayofweek<5)].reset_index(drop=True)
