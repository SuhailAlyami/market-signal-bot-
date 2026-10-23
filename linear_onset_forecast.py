"""Fixed causal, uncalibrated readiness forecast; never imported by live senders."""
import numpy as np
import pandas as pd
from compare_amd_reclaim import rolling_features
from hunter_linear_research import fit_model

VERSION='native-linear-onset-watch-v1'
NAMES=['trend5','trend15','body_atr','span_atr','rvol','contraction','position5','width5_atr']


def feature_matrix(minute):
    base=rolling_features(minute);atr=base.atr
    high5=minute.High.rolling(5).max();low5=minute.Low.rolling(5).min()
    width=high5-low5;wide=minute.High.rolling(20).max()-minute.Low.rolling(20).min()
    f=pd.DataFrame(dict(trend5=(minute.Close-minute.Close.shift(5))/atr,
        trend15=(minute.Close-minute.Close.shift(15))/atr,body_atr=(minute.Close-minute.Open)/atr,
        span_atr=(minute.High-minute.Low)/atr,rvol=base.rvol,contraction=width/wide,
        position5=2*(minute.Close-low5)/width-1,width5_atr=width/atr),index=minute.index)
    f['valid']=base.valid & np.isfinite(f[NAMES]).all(axis=1) & width.gt(0) & wide.gt(0)
    return f


def training_labels(minute,indices,events):
    labels=np.zeros(len(indices),dtype=int);lookup={i:k for k,i in enumerate(indices)}
    ambiguous=set()
    for event in events:
        onset=pd.Timestamp(event['onset_time']);label=1 if event['direction']==1 else 2
        for i in range(int(event['anchor_index']),int(event['target_index'])):
            if i not in lookup or event['target_index']>i+10:continue
            lead=(onset-(minute.index[i]+pd.Timedelta(minutes=1))).total_seconds()/60
            if not 1<=lead<=3:continue
            k=lookup[i]
            if labels[k] not in (0,label):ambiguous.add(k)
            labels[k]=label
    keep=np.array([k not in ambiguous for k in range(len(indices))])
    return labels,keep


def fit(features,indices,labels,keep):
    selected=np.array(indices)[keep];y=labels[keep];counts=np.bincount(y,minlength=3)
    if min(counts[1:])<10:raise ValueError('insufficient_training_directional_support')
    model=fit_model(features.iloc[selected][NAMES].to_numpy(),y,1.,iterations=300)
    return dict(version=VERSION,feature_names=NAMES,**model)


def scores(features,model):
    x=features[NAMES].to_numpy()
    z=np.column_stack((np.ones(len(x)),np.clip((x-np.array(model['center']))/np.array(model['scale']),-8,8)))
    logits=z@np.array(model['weights']);logits-=np.max(logits,axis=1,keepdims=True)
    exp=np.exp(logits);return exp/exp.sum(axis=1,keepdims=True)


def warnings(minute,features,model,indices):
    probabilities=scores(features,model);signals=[];active=0;previous=None
    for i in indices:
        if previous is not None and minute.index[i]-minute.index[previous]!=pd.Timedelta(minutes=1):active=0
        previous=i
        if not features.valid.iloc[i]:active=0;continue
        p=probabilities[i]
        if active and p[1 if active==1 else 2]<.5:active=0
        choice=int(np.argmax(p));other=2 if choice==1 else 1
        if choice==0 or p[choice]<.65 or p[choice]-p[other]<.1:continue
        side=1 if choice==1 else -1
        if active==side:continue
        active=side;start=minute.index[i]
        signals.append(dict(index=int(i),direction=side,bar_time=start.isoformat(),
            detected_at=(start+pd.Timedelta(minutes=1)).isoformat(),state='WATCH',rule_version=VERSION,
            readiness='NOT_READY',notify_eligible=False,score=float(p[choice]),calibrated_probability=False))
    return signals
