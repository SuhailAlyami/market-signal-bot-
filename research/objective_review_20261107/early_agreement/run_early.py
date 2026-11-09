"""Single predeclared timeframe change; offline SPX research."""
import argparse
import gzip
import hashlib
import json
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from objective_review import RIYADH,input_bytes,load_sessions
from ensemble_audit.audit import combine,constituent_events
from wave_capture.run import aggregate5,atr_before,coverage,detect,match_legs,reference_legs,score,summarize


def fast_events(bars):
    out = [dict(e,method='wave') for e in detect(bars)]
    if len(bars)<7:
        return out
    low,high = min(b.low for b in bars[:6]),max(b.high for b in bars[:6])
    found = set()
    for i in range(6,len(bars)):
        b,prior = bars[i],bars[i-1]
        breakout = 1 if b.close>high else -1 if b.close<low else 0
        reclaim = (1 if prior.close<low and b.low<low and low<b.close<high else
                   -1 if prior.close>high and b.high>high and low<b.close<high else 0)
        for method,side in [('breakout',breakout),('reclaim',reclaim)]:
            if side and method not in found:
                found.add(method)
                out.append(dict(index=i,decision=b.at+timedelta(minutes=5),side=side,
                                r=max(5.0,atr_before(bars,i)),method=method))
    return out


def paired_change(rows,days,delay=0):
    daily = {day:0.0 for day in days}
    for row in rows:
        if row['day'] in daily and row['delay']==delay and row['outcome']['status']=='SCORED':
            sign = 1 if row['variant']=='fast5' else -1
            daily[row['day']] += sign*(row['outcome']['gross_low']-1)
    values = list(daily.values())
    rng = random.Random(714)
    samples = sorted(sum(rng.choices(values,k=len(values))) for _ in range(1000))
    return {'fast_minus_control_cost1':round(sum(values),3),
            'paired_session_bootstrap95':[round(samples[24],3),round(samples[974],3)]}


def run(data,protocol):
    sessions,excluded = load_sessions(data)
    rows,matrix = [],[]
    for day,raw,bars15,step,closing in sessions:
        bars = aggregate5(raw,step)
        events = {'control15':combine(constituent_events(bars,bars15),True),
                  'fast5':combine(fast_events(bars),True)}
        legs = reference_legs(bars)
        for variant,signals in events.items():
            matrix.extend(dict(r,day=day,variant=variant) for r in match_legs(bars,signals,legs))
            for e in signals:
                for delay in (0,15,60):
                    outcome = score(raw,step,closing,e,e['side'],delay)
                    rows.append(dict(day=day,variant=variant,index=e['index'],side=e['side'],r=e['r'],delay=delay,
                                     support=e['support'],decision_Riyadh=e['decision'].astimezone(RIYADH).isoformat(),
                                     outcome=outcome))
    groups = {'older':[s[0] for s in sessions if s[0]<'2026-09-14'],
              'recent':[s[0] for s in sessions if s[0]>='2026-09-14'],'all':[s[0] for s in sessions]}
    report = {}
    for group,days in groups.items():
        subset = [r for r in rows if r['day'] in set(days)]
        report[group] = {'sessions':len(days),'variants':{}}
        for variant in ('control15','fast5'):
            own = [r for r in subset if r['variant']==variant]
            report[group]['variants'][variant] = {
                'coverage':coverage([r for r in matrix if r['day'] in set(days) and r['variant']==variant],sum(r['delay']==0 for r in own)),
                'execution':{str(d):summarize([r['outcome'] for r in own if r['delay']==d]) for d in (0,15,60)}}
        report[group]['paired_comparison'] = {str(d):paired_change(subset,days,d) for d in (0,15,60)}
        # Pair identical reference legs: matched-set differences are not paired timing improvements.
        by_variant = {v:{(r['day'],r['start'],r['end']):r for r in matrix
                         if r['day'] in set(days) and r['variant']==v and r['matched']}
                      for v in ('control15','fast5')}
        common = set(by_variant['fast5'])&set(by_variant['control15'])
        diffs = [by_variant['fast5'][k]['lag_minutes']-by_variant['control15'][k]['lag_minutes'] for k in common]
        import statistics
        report[group]['common_leg_timing'] = {'common_matched_legs':len(common),
            'median_fast_minus_control_lag_minutes':statistics.median(diffs) if diffs else None,
            'earlier':sum(v<0 for v in diffs),'later':sum(v>0 for v in diffs),'same':sum(v==0 for v in diffs),
            'gained_matched_legs':len(set(by_variant['fast5'])-set(by_variant['control15'])),
            'lost_matched_legs':len(set(by_variant['control15'])-set(by_variant['fast5']))}
    passed = all(report[g]['variants']['fast5']['execution']['0']['net_lower']['1']>0 for g in ('older','recent'))
    passed &= report['recent']['paired_comparison']['0']['paired_session_bootstrap95'][0]>0
    passed &= all(report[g]['variants']['fast5']['coverage']['early_before25pct']>=
                  report[g]['variants']['control15']['coverage']['early_before25pct'] for g in ('older','recent'))
    return {'status':'NOT_READY_RESEARCH_ONLY','decision':'UNUSED_PROSPECTIVE_TEST_ONLY' if passed else 'REJECT_CHANGE_KEEP_CONTROL_RESEARCH_ONLY',
            'input_sha256':hashlib.sha256(input_bytes(data)).hexdigest(),
            'protocol_sha256':hashlib.sha256(protocol.read_bytes()).hexdigest(),
            'excluded_sessions':excluded,'report':report,'events':rows,'coverage_matrix':matrix}


if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('opening_validation_raw.json.gz'))
    p.add_argument('--protocol',type=Path,default=Path('early_agreement/protocol.json'))
    p.add_argument('--out',type=Path,default=Path('early_agreement/results.json.gz'))
    args = p.parse_args()
    result = run(args.data,args.protocol)
    payload = (json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    args.out.write_bytes(gzip.compress(payload,mtime=0) if args.out.suffix=='.gz' else payload)
    print(json.dumps({k:v for k,v in result.items() if k not in ('events','coverage_matrix')},indent=2))
