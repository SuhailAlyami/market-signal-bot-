"""Big-move ('explosion') prediction research, 2026-11-24.
Target: |close-open| >= 0.75 m (same as range_alert/explosion.py). Pre-open features only.
Selection: walk-forward on 2015-2019 (each year predicted by a model fit on earlier years only).
Final: ONE walk-forward run on 2020-2026 for the selected variant vs the current model."""
import gzip, json, math, sys, datetime as dt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
sys.path.insert(0, '/home/claude/market-signal-bot-/range_alert')
import explosion as X
D='vrp/research/volatility_premium_20261115/'
def load(n):
    r=json.load(gzip.open(D+n))['chart']['result'][0]; q=r['indicators']['quote'][0]; o={}
    for i,t in enumerate(r['timestamp']):
        v=[q[k][i] for k in ('open','high','low','close')]
        if None not in v: o[dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat()]=tuple(v)
    return o
spx=load('GSPC_1d.json.gz'); vixo=load('VIX_1d.json.gz'); vix={d:v[3] for d,v in vixo.items()}
spx={d:v for d,v in spx.items() if d>='2008-06-01'}
data=X.dataset(spx,vix)
days=[d for d,*_ in data]; Xb=np.array([f for _,f,_,_ in data]); y=np.array([e for _,_,e,_ in data]).astype(int)
yr=np.array([int(d[:4]) for d in days])
alld=sorted(spx)
def third_friday(d):
    return d.weekday()==4 and 15<=d.day<=21
def cal_feats(ds):
    out=[]
    idx={d:i for i,d in enumerate(alld)}
    for s in ds:
        d=dt.date.fromisoformat(s); i=idx[s]
        prev=dt.date.fromisoformat(alld[i-1]); nxt=dt.date.fromisoformat(alld[i+1]) if i+1<len(alld) else d+dt.timedelta(1)
        first_of_month = prev.month!=d.month
        out.append([third_friday(d), first_of_month, (d-prev).days>3, (nxt-d).days>3 and d.weekday()!=4,
                    d.month==12 and d.day>=20])
    return np.array(out,dtype=float)
Xc=cal_feats(days)
# extra market features: VIX open gap (VIX overnight not available pre-open on daily data -> skip), VIX 5d trend, prior explosion flags
def extra(ds):
    out=[]
    for k,s in enumerate(ds):
        i=alld.index(s) if False else None
    return None
def lr_fit_pred(Xtr,ytr,Xte):
    mu,sd=Xtr.mean(0),Xtr.std(0)+1e-12
    m=LogisticRegression(max_iter=3000).fit((Xtr-mu)/sd,ytr); return m.predict_proba((Xte-mu)/sd)[:,1]
def gb_fit_pred(Xtr,ytr,Xte):
    m=HistGradientBoostingClassifier(max_depth=3,learning_rate=0.05,max_iter=200,min_samples_leaf=80,l2_regularization=1.0,random_state=0).fit(Xtr,ytr)
    return m.predict_proba(Xte)[:,1]
def wf(Xm,fitpred,years,min_train_year=2009):
    P=[];Y=[]
    for Yr in years:
        tr=(yr<Yr)&(yr>=min_train_year); te=yr==Yr
        if te.sum()==0: continue
        P+=list(fitpred(Xm[tr],y[tr],Xm[te])); Y+=list(y[te])
    P,Y=np.array(P),np.array(Y); q=np.quantile(P,.9)
    return dict(auc=round(roc_auc_score(Y,P),3),top10=round(100*Y[P>=q].mean(),1),rest=round(100*Y[P<q].mean(),1),n=len(Y),base=round(100*Y.mean(),1))
variants={'base_lr':(Xb,lr_fit_pred),'base+cal_lr':(np.hstack([Xb,Xc]),lr_fit_pred),
          'base_gb':(Xb,gb_fit_pred),'base+cal_gb':(np.hstack([Xb,Xc]),gb_fit_pred)}
stage=sys.argv[1] if len(sys.argv)>1 else 'select'
if stage=='select':
    for k,(Xm,fp) in variants.items(): print('SELECT 2015-2019',k,wf(Xm,fp,range(2015,2020)))
else:
    for k in sys.argv[2:]:
        Xm,fp=variants[k]; print('TEST 2020-2026',k,wf(Xm,fp,range(2020,2027)))
