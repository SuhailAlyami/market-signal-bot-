"""Bounded nonlinear research comparator; no runtime integration or alerts.

Uses exactly the chronological labels, splits and selection objective of the
linear comparator. Source data are reused, not an untouched holdout.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn import __version__ as sklearn_version
from sklearn.ensemble import HistGradientBoostingClassifier

from hunter_linear_research import run


STRENGTHS=(1.,10.,100.)


def fit_boosted(x,y,regularization):
    if len(x)<100 or len(np.unique(y))<3:
        raise ValueError('insufficient_training_classes')
    counts=np.bincount(y,minlength=3)
    importance=len(y)/(3*counts[y])
    estimator=HistGradientBoostingClassifier(max_leaf_nodes=7,max_iter=100,
                min_samples_leaf=80,learning_rate=.05,l2_regularization=regularization,
                early_stopping=False,random_state=17)
    estimator.fit(x,y,sample_weight=importance)
    return {'kind':'hist_gradient_boosting','_estimator':estimator,
            'regularization':regularization,'train_rows':len(y),'class_counts':counts.tolist(),
            'parameters':estimator.get_params(),'sklearn_version':sklearn_version,
            'calibrated_probability':False}


def public_report(value):
    if isinstance(value,dict):
        return {key:public_report(item) for key,item in value.items() if not key.startswith('_')}
    if isinstance(value,list):return [public_report(item) for item in value]
    return value


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
        r=public_report(run(frames[sym],frames[other],sym,pd.Timestamp(a.as_of),
                            fitter=fit_boosted,strengths=STRENGTHS))
        r['source_sha256']={s:hashlib.sha256(Path(path).read_bytes()).hexdigest() for s,path in (('ES',a.es),('NQ',a.nq))}
        r['experiment']='bounded_histogram_boosting_v2'
        (output/(sym.lower()+'_report.json')).write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
        print(json.dumps({'symbol':sym,'regularization':r['selected']['params']['model']['regularization'],
                          'threshold':r['selected']['params']['threshold'],'test':r['results']['test']['selected']}),flush=True)
