"""Frozen close-only direction experiment. Never used by the issued OHLC model."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from spx_daily import schedule

VERSION='spx-close-ridge-v1'
CLASSES=('Bullish','Bearish','Sideways')


def direction(previous, current):
    change=current/previous-1
    return 'Bullish' if change>.001 else 'Bearish' if change<-.001 else 'Sideways'


def load_exports(first_path, second_path):
    def read(path, period):
        encoded=Path(path).read_bytes(); data=json.loads(encoded)
        expected=dict(contract_id=416904,exchange='CBOE',outside_rth=False,
                      period=period,security_type='IND',step='ONE_DAY')
        if data['request']!=expected:
            raise ValueError('wrong native history request')
        response=data['response']
        if response.get('chart_step')!=86400:
            raise ValueError('not daily data')
        if len({len(response[k]) for k in ('time','open','high','low','close')})!=1:
            raise ValueError('unequal export array lengths')
        rows=[]
        for i,text in enumerate(response['time']):
            stamp=pd.Timestamp(text)
            if stamp.tzinfo is None:raise ValueError('timezone missing')
            day=str(stamp.tz_convert('America/New_York').date())
            if not '2024-10-28'<=day<='2025-12-31':continue
            close=float(response['close'][i])
            if not np.isfinite(close) or close<=0:raise ValueError('invalid close')
            rows.append(dict(date=day,close=close))
        expected_dates=[str(d.date()) for d in schedule('2024-10-28','2025-12-31').index]
        if [r['date'] for r in rows]!=expected_dates:
            raise ValueError('missing, duplicate or unordered close session')
        return rows,hashlib.sha256(encoded).hexdigest()
    rows,a=read(first_path,'TWO_YEARS'); other,b=read(second_path,'FIVE_YEARS')
    if rows!=other:raise ValueError('close exports disagree')
    return rows,dict(two_year_sha256=a,five_year_sha256=b)


def features(rows):
    close=pd.Series([r['close'] for r in rows],dtype=float)
    returns=close.pct_change()
    x=pd.DataFrame({f'return_{n}':close.pct_change(n) for n in (1,3,5,10,20)})
    x['vol_5']=returns.rolling(5).std()
    x['vol_20']=returns.rolling(20).std()
    x['sma_20']=close/close.rolling(20).mean()-1
    x['drawdown_20']=close/close.rolling(20).max()-1
    return close,x


def predict(rows):
    if len(rows)<81:raise ValueError('need 81 sessions')
    close,x=features(rows)
    valid=np.flatnonzero(np.isfinite(x.to_numpy()).all(axis=1))
    if len(rows)-1 not in valid:raise ValueError('invalid latest features')
    train=valid[valid<len(rows)-1][-252:]
    if len(train)<40:raise ValueError('need 40 labeled examples')
    center=x.iloc[train].mean();scale=x.iloc[train].std(ddof=0).replace(0,1)
    z=((x.iloc[train]-center)/scale).clip(-5,5).to_numpy()
    latest=((x.iloc[-1]-center)/scale).clip(-5,5).to_numpy()
    design=np.column_stack([np.ones(len(train)),z])
    labels=[direction(close.iloc[i],close.iloc[i+1]) for i in train]
    y=np.array([[float(label==k) for k in CLASSES] for label in labels])
    penalty=np.eye(design.shape[1])*10;penalty[0,0]=0
    coefficients=np.linalg.solve(design.T@design+penalty,design.T@y)
    scores=np.r_[1,latest]@coefficients
    predicted=CLASSES[int(np.argmax(scores))]
    return dict(direction=predicted,confidence=None,model_version=VERSION,
                class_scores={k:float(v) for k,v in zip(CLASSES,scores)},
                status='RESEARCH_NOT_VALIDATED',training_examples=len(train))


def metrics(records, key):
    confusion={actual:{pred:0 for pred in CLASSES} for actual in CLASSES}
    for row in records:confusion[row['actual']][row[key]]+=1
    recalls={k:confusion[k][k]/sum(confusion[k].values())
             for k in CLASSES if sum(confusion[k].values())}
    return dict(count=len(records),accuracy=sum(r[key]==r['actual'] for r in records)/len(records),
                balanced_accuracy=float(np.mean(list(recalls.values()))),
                class_recall=recalls,confusion=confusion)


def segment(rows,start,stop):
    records=[]
    for n in range(start,stop):
        prefix=rows[:n]; predicted=predict(prefix)
        labels=[direction(a['close'],b['close']) for a,b in zip(prefix,prefix[1:])]
        records.append(dict(date=rows[n]['date'],candidate=predicted['direction'],
            actual=direction(rows[n-1]['close'],rows[n]['close']),
            majority=max(CLASSES,key=labels.count),previous=labels[-1],
            momentum_5=direction(rows[n-6]['close'],rows[n-1]['close'])))
    stats={key:metrics(records,key) for key in ('candidate','majority','previous','momentum_5')}
    candidate=stats['candidate']; comparisons={}
    for key in ('majority','previous','momentum_5'):
        delta=np.array([int(r['candidate']==r['actual'])-int(r[key]==r['actual']) for r in records])
        rng=np.random.default_rng(20261026)
        lower=float(np.quantile(rng.choice(delta,size=(2000,len(delta))).mean(axis=1),.025))
        comparisons[key]=dict(accuracy_gain=candidate['accuracy']-stats[key]['accuracy'],
            paired_gain_lower_95=lower,passed=candidate['accuracy']-stats[key]['accuracy']>=.05-1e-12 and lower>0)
    passed=(len(records)>=60 and len(candidate['class_recall'])==3 and
            candidate['balanced_accuracy']>=.45 and all(r['passed'] for r in comparisons.values()))
    return dict(passed=passed,metrics=stats,comparisons=comparisons,records=records)


def evaluate(rows):
    dates=[r['date'] for r in rows]
    v,h=dates.index('2025-04-01'),dates.index('2025-07-01')
    if v<81 or h-v<60 or len(rows)-h<60:raise ValueError('insufficient fixed split')
    report=dict(model=VERSION,status='NOT_READY',target='next_close_change_0.1_percent',
                first=dates[0],last=dates[-1],validation_start=dates[v],holdout_start=dates[h],
                high_low_used=False,confidence=None,holdout_evaluated=False,
                input_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
    report['validation']=segment(rows,v,h)
    if report['validation']['passed']:
        report['holdout']=segment(rows,h,len(rows));report['holdout_evaluated']=True
        if report['holdout']['passed']:report['status']='SHADOW_REQUIRED'
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--first',required=True);p.add_argument('--second',required=True);p.add_argument('--output',required=True)
    args=p.parse_args()
    # Reserve before computation so rerunning cannot silently consume outcomes.
    with Path(args.output).open('x',encoding='utf-8') as stream:
        rows,hashes=load_exports(args.first,args.second)
        report=evaluate(rows);report['source_hashes']=hashes
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k not in ('validation','holdout')}))
    print(json.dumps(report['validation']['metrics'],indent=2))
