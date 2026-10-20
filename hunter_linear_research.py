"""Train-only regularized multinomial scores; no calibrated trading probability.

All selection remains inside train/validation. The retained source dataset has
already been used in other experiments; test reports are retrospective reuse.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from hunter_crossmarket_research import paired_features
from hunter_research import (BASELINES, ResearchConfig, _evaluation_context, _evaluate,
                             _session_labels, candidate_signal, chronological_splits,
                             score_signals, selection_score)

REGULARIZATION = (.01, .1, 1.)
THRESHOLDS = (.35, .5, .65)


def matrix_features(data,other):
    f=paired_features(data,other)
    local=data.index.tz_convert('America/New_York')
    time=(local.hour*60+local.minute).to_numpy()/1440*2*np.pi
    values=[f.rvol,f.move,f.trend_5,f.trend_15,f.acceleration,f.contraction,
            (f.close-f.range_high)/f.atr,(f.close-f.range_low)/f.atr,f.span/f.atr,
            f.local_width,(f.close-f.local_high)/f.atr,(f.close-f.local_low)/f.atr,
            f.other_trend,f.close_position,np.sin(time),np.cos(time)]
    for i,column in enumerate(values):f[f'm{i}']=column
    f['model_valid']=f.valid & f.other_valid & np.isfinite(f[[f'm{i}' for i in range(16)]]).all(axis=1)
    return f


def fit_model(x,y,regularization,iterations=300):
    if len(x)<100 or len(np.unique(y))<3:
        raise ValueError('insufficient_training_classes')
    center=np.median(x,axis=0)
    scale=np.maximum(np.quantile(x,.75,axis=0)-np.quantile(x,.25,axis=0),1e-6)
    z=np.column_stack((np.ones(len(x)),np.clip((x-center)/scale,-8,8)))
    weights=np.zeros((z.shape[1],3))
    counts=np.bincount(y,minlength=3)
    importance=len(y)/(3*counts[y])
    target=np.eye(3)[y]
    for _ in range(iterations):
        logits=z@weights
        exp=np.exp(logits-logits.max(axis=1,keepdims=True))
        p=exp/exp.sum(axis=1,keepdims=True)
        penalty=regularization*weights
        penalty[0]=0
        gradient=z.T@((p-target)*importance[:,None])/len(y)+penalty
        weights-=.08*gradient
    return {'center':center.tolist(),'scale':scale.tolist(),'weights':weights.tolist(),
            'regularization':regularization,'train_rows':len(y),'class_counts':counts.tolist(),
            'iterations':iterations,'calibrated_probability':False}


def predict_score(row,model):
    x=np.array([row[f'm{i}'] for i in range(16)])
    if model.get('kind')=='hist_gradient_boosting':
        return model['_estimator'].predict_proba(x.reshape(1,-1))[0]
    z=np.r_[1.,np.clip((x-np.array(model['center']))/np.array(model['scale']),-8,8)]
    logits=z@np.array(model['weights'])
    exp=np.exp(logits-logits.max())
    return exp/exp.sum()


def rule(row,method,params):
    if method in BASELINES:return candidate_signal(row,method,params)
    if not row['model_valid']:return 0
    score=predict_score(row,params['model'])
    choice=int(np.argmax(score))
    other=2 if choice==1 else 1
    if choice==0 or score[choice]<params['threshold'] or score[choice]-score[other]<.1:return 0
    return 1 if choice==1 else -1


def fit_for(data,f,indices,config,regularization,fitter=None):
    context=_evaluation_context(data,f,indices,'rth',config)
    eligible=[i for i in context['eligible'] if f.model_valid.iloc[i]]
    positions={idx:j for j,idx in enumerate(eligible)}
    y=np.zeros(len(eligible),dtype=int)
    for event in context['events']:
        for i in range(event['anchor_index'],event['onset_index']):
            if i in positions:y[positions[i]]=1 if event['direction']==1 else 2
    x=f.iloc[eligible][[f'm{i}' for i in range(16)]].to_numpy()
    return (fitter or fit_model)(x,y,regularization)


def run(data,other,symbol,as_of,*,fitter=None,strengths=REGULARIZATION):
    config=ResearchConfig(bootstrap_samples=500)
    data=data.loc[data.index+pd.Timedelta(minutes=1)<=as_of]
    f=matrix_features(data,other)
    splits,inventory=chronological_splits(data,'rth',as_of,config.horizon)
    labels=_session_labels(data.index,'rth')
    contexts={phase:_evaluation_context(data,f,idx,'rth',config) for phase,idx in splits.items()}
    train_days=sorted(set(labels[splits['train']]))
    ranking=[]
    for strength in strengths:
        folds=[]
        for end in (len(train_days)//2,3*len(train_days)//4):
            stop=min(end+max(1,len(train_days)//4),len(train_days))
            before=[i for i in splits['train'] if labels[i] in train_days[:end]][:-config.horizon]
            after=[i for i in splits['train'] if labels[i] in train_days[end:stop]][config.horizon:-config.horizon]
            model=fit_for(data,f,before,config,strength,fitter)
            metrics,_,_=_evaluate(data,f,after,'linear',{'model':model,'threshold':.5},'rth',config,signal_rule=rule)
            folds.append({'earlier_days':train_days[:end],'next_days':train_days[end:stop],
                          'early_f1':selection_score(metrics),'metrics':metrics})
        ranking.append({'regularization':strength,'mean_train_fold_early_f1':float(np.mean([x['early_f1'] for x in folds])),
                        'folds':folds})
    ranked=sorted(ranking,key=lambda x:(-x['mean_train_fold_early_f1'],x['regularization']))[:2]
    candidates=[]
    for item in ranked:
        model=fit_for(data,f,splits['train'],config,item['regularization'],fitter)
        for threshold in THRESHOLDS:
            params={'model':model,'threshold':threshold}
            m,_,_=_evaluate(data,f,splits['validation'],'linear',params,'rth',config,
                            _context=contexts['validation'],signal_rule=rule)
            candidates.append({'params':params,'validation':m,'early_f1':selection_score(m)})
    supported=[c for c in candidates if c['validation']['signals']>=3]
    selected=sorted(supported or candidates,key=lambda c:(-c['early_f1'],c['validation']['false_alarms'],
                                            c['params']['model']['regularization'],c['params']['threshold']))[0]
    # No refitting or threshold selection after this point.
    results={};artifacts={};delays={}
    for phase,idx in splits.items():
        m,e,s=_evaluate(data,f,idx,'linear',selected['params'],'rth',config,True,
                        _context=contexts[phase],signal_rule=rule)
        baselines={}
        for method in BASELINES:
            bm,_,_=_evaluate(data,f,idx,method,{'rvol':1.3},'rth',config,True,
                             _context=contexts[phase],signal_rule=rule)
            baselines[method]=bm
        results[phase]={'selected':m,'baselines':baselines}
        if phase=='test':
            artifacts={'events':e,'signals':s}
            eligible=contexts[phase]['eligible']
            for delay in (0,1,2,5,10):
                delays[str(delay)]=score_signals(e,[dict(row) for row in s if row['outcome_observable']],
                                               data,eligible,'rth',config,True,delay)
    return {'status':'NOT_READY','symbol':symbol,'dataset_reused':True,'independent_untouched_holdout':False,
            'minimum_validation_support_met':bool(supported),
            'session_inventory':inventory,'train_only_walkforward':ranking,'validation_candidates':candidates,
            'selected':selected,'results':results,'test_artifacts':artifacts,
            'test_latency_sensitivity_minutes':delays,
            'notifications_enabled':False,'calibrated_probability':False,
            'limitations':['Related ES/NQ minute bars and overlapping labels are correlated.',
                           'Prior reports already used this dataset; this is retrospective chronological evaluation.',
                           'No live option chain, option returns, fills, execution costs or profit are modeled.',
                           'No independent prospective validation or reliable early detector is established.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--es',required=True);p.add_argument('--nq',required=True)
    p.add_argument('--output',required=True);p.add_argument('--as-of',required=True)
    a=p.parse_args();frames={}
    for sym,path in (('ES',a.es),('NQ',a.nq)):
        frames[sym]=pd.read_csv(path,index_col=0,parse_dates=True)
        frames[sym].index=pd.to_datetime(frames[sym].index,utc=True)
    output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
    for sym,other in (('ES','NQ'),('NQ','ES')):
        r=run(frames[sym],frames[other],sym,pd.Timestamp(a.as_of))
        r['source_sha256']={s:hashlib.sha256(Path(path).read_bytes()).hexdigest() for s,path in (('ES',a.es),('NQ',a.nq))}
        (output/(sym.lower()+'_report.json')).write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
        print(json.dumps({'symbol':sym,'regularization':r['selected']['params']['model']['regularization'],
                          'threshold':r['selected']['params']['threshold'],'test':r['results']['test']['selected']}),flush=True)
