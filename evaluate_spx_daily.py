"""Chronological daily benchmark; no tuning or automatic model promotion."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import numpy as np
from spx_daily import connect, ingest, forecast, features, direction
from spx_daily_regime import forecast_regime, CLASSES, VERSION


def naive(rows):
    f, _, atr = features(rows)
    labels = [direction(f.close.iloc[i]-f.close.iloc[i-1],atr.iloc[i-1])
              for i in range(21,len(f))]
    return dict(direction=max(CLASSES,key=labels.count),atr=float(atr.iloc[-1]),
                predicted_high=float(f.close.iloc[-1]+atr.iloc[-1]/2),
                predicted_low=float(f.close.iloc[-1]-atr.iloc[-1]/2))


def score(prediction, actual, previous):
    actual_direction = direction(actual['close']-previous['close'],prediction['atr'])
    return dict(date=actual['date'],direction=prediction['direction'],actual_direction=actual_direction,
                direction_accuracy=int(prediction['direction']==actual_direction),
                predicted_high=prediction['predicted_high'],predicted_low=prediction['predicted_low'],
                actual_high=actual['high'],actual_low=actual['low'],
                high_error=prediction['predicted_high']-actual['high'],
                low_error=prediction['predicted_low']-actual['low'])


def metrics(records):
    recalls = {k:float(np.mean([r['direction_accuracy'] for r in records if r['actual_direction']==k]))
               for k in CLASSES if any(r['actual_direction']==k for r in records)}
    return dict(count=len(records),direction_accuracy=float(np.mean([r['direction_accuracy'] for r in records])),
                balanced_accuracy=float(np.mean(list(recalls.values()))),class_recall=recalls,
                high_mae=float(np.mean([abs(r['high_error']) for r in records])),
                low_mae=float(np.mean([abs(r['low_error']) for r in records])))


def compare(candidate, baseline):
    if [r['date'] for r in candidate] != [r['date'] for r in baseline]:
        raise ValueError('paired dates required')
    a,b=metrics(candidate),metrics(baseline)
    delta=np.array([x['direction_accuracy']-y['direction_accuracy'] for x,y in zip(candidate,baseline)])
    rng=np.random.default_rng(20261026)
    lower=float(np.quantile(rng.choice(delta,size=(2000,len(delta))).mean(axis=1),.025))
    checks=dict(sample_size=len(candidate)>=60,
                all_actual_classes=len(a['class_recall'])==3,
                direction_gain=a['direction_accuracy']-b['direction_accuracy']>=.05-1e-12,
                paired_gain_lower_positive=lower>0,
                balanced_accuracy=a['balanced_accuracy']>=.45,
                boundary_gain=a['high_mae']+a['low_mae']<=.95*(b['high_mae']+b['low_mae']),
                high_not_worse=a['high_mae']<=b['high_mae'],
                low_not_worse=a['low_mae']<=b['low_mae'])
    return dict(passed=all(checks.values()),checks=checks,paired_gain_lower_95=lower)


def segment(rows, start, stop):
    result={k:[] for k in ('v1','v2','v3','naive')}
    for n in range(start,stop):
        prefix=rows[:n]
        predictions={'v1':forecast(prefix,False),'v2':forecast(prefix),
                     'v3':forecast_regime(prefix),'naive':naive(prefix)}
        for k,p in predictions.items():
            result[k].append(score(p,rows[n],rows[n-1]))
    gates={k:compare(result['v3'],result[k]) for k in ('v2','naive')}
    return dict(metrics={k:metrics(v) for k,v in result.items()},gates=gates,
                passed=all(g['passed'] for g in gates.values()),records=result)


def evaluate(rows, validation_start, holdout_start):
    dates=[r['date'] for r in rows]
    if validation_start not in dates or holdout_start not in dates:
        raise ValueError('split dates must be actual input sessions')
    v,h=dates.index(validation_start),dates.index(holdout_start)
    if v<81 or h-v<60 or len(rows)-h<60:
        raise ValueError('need >=81 train, >=60 validation, >=60 holdout sessions')
    report=dict(model=VERSION,status='NOT_READY',
                validation_start=validation_start,holdout_start=holdout_start,
                input_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
                holdout_evaluated=False)
    report['validation']=segment(rows,v,h)
    if not report['validation']['passed']:
        return report
    report['holdout']=segment(rows,h,len(rows))
    report['holdout_evaluated']=True
    if report['holdout']['passed']:
        report['status']='SHADOW_REQUIRED'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--validation-start',required=True)
    parser.add_argument('--holdout-start',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    document=json.loads(Path(args.input).read_text(encoding='utf-8'))
    try:
        with closing(connect(':memory:')) as db:
            rows=ingest(db,document)
    except (ValueError, KeyError, TypeError) as exc:
        report=dict(model=VERSION,status='WAIT_VALID_DATA',reason=str(exc),
                    input_sha256=hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest(),
                    holdout_evaluated=False)
    else:
        report=evaluate(rows,args.validation_start,args.holdout_start)
    # Refuse overwriting a prior report, including negative outcomes.
    with Path(args.output).open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(dict(status=report['status'],holdout_evaluated=report['holdout_evaluated'])))
