"""Causal detector ensembles and hindsight complementarity, offline only."""
import argparse
import gzip
import hashlib
import json
import random
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from objective_review import RIYADH, first_event, input_bytes, load_sessions
from wave_capture.run import aggregate5, atr_before, coverage, detect, match_legs, reference_legs, score, summarize

METHODS = ('reclaim','breakout','wave','union','consensus')


def combine(events, consensus=False):
    """Input events carry method identity; outputs depend on closed events only."""
    grouped = defaultdict(list)
    for event in events:
        grouped[event['decision']].append(event)
    last, outputs, last_emit = {}, [], None
    for at in sorted(grouped):
        current = grouped[at]
        # Every method has at most one event at this close.
        if len({e['method'] for e in current}) != len(current):
            raise ValueError('Duplicate method at one close')
        for event in current:
            last[event['method']] = event
        if consensus:
            fresh = {m:e for m,e in last.items() if at-e['decision'] <= timedelta(minutes=15)}
            sides = [side for side in (-1,1) if sum(e['side']==side for e in fresh.values()) >= 2
                     and any(e['side']==side for e in current)]
        else:
            sides = list({e['side'] for e in current})
        if len(sides)!=1 or (last_emit is not None and at-last_emit < timedelta(minutes=30)):
            continue
        side = sides[0]
        support = sorted(m for m,e in (fresh.items() if consensus else
                         ((e['method'],e) for e in current)) if e['side']==side)
        source = current[0]
        outputs.append(dict(source,side=side,method='consensus' if consensus else 'union',support=support))
        last_emit = at
    return outputs


def constituent_events(bars5,bars15):
    mapped = {b.at+timedelta(minutes=5):i for i,b in enumerate(bars5)}
    events = [dict(e,method='wave') for e in detect(bars5)]
    for method, original in [('reclaim','reclaim_30m'),('breakout','breakout_90m')]:
        e = first_event(bars15,original)
        if e:
            i = mapped[e['decision']]
            r = max(5.0,atr_before(bars5,i))
            events.append(dict(index=i,decision=e['decision'],side=e['side'],r=r,method=method))
    return events


def bootstrap_difference(rows,days):
    daily = {day:0.0 for day in days}
    for row in rows:
        if row['candidate']['status']=='SCORED' and row['up']['status']=='SCORED':
            daily[row['day']] += row['candidate']['gross_low']-row['up']['gross_low']
    values = list(daily.values())
    rng = random.Random(713)
    draws = sorted(sum(rng.choices(values,k=len(values))) for _ in range(1000))
    return {'candidate_minus_always_up_cost1':round(sum(values),3),
            'paired_session_bootstrap_95':[round(draws[24],3),round(draws[974],3)]}


def complementarity(matrix,methods):
    result = {}
    for kind in ('matched','early'):
        sets = {m:{(r['day'],r['start'],r['end']) for r in matrix
                   if r['method']==m and r[kind]} for m in methods}
        union = set().union(*sets.values())
        result[kind] = {'raw_union_ceiling':len(union),
            'unique_by_method': {m:len(sets[m]-set().union(*(sets[o] for o in methods if o!=m))) for m in methods},
            'shared_all':len(set.intersection(*sets.values())),
            'pairwise_overlap':{a+'|'+b:len(sets[a]&sets[b]) for i,a in enumerate(methods) for b in methods[i+1:]}}
    return result


def run(data,protocol):
    sessions, excluded = load_sessions(data)
    rows, matrix = [], []
    for day,raw,bars15,step,closing in sessions:
        bars5 = aggregate5(raw,step)
        base = constituent_events(bars5,bars15)
        by_method = {m:[e for e in base if e['method']==m] for m in METHODS[:3]}
        by_method.update(union=combine(base),consensus=combine(base,True))
        legs = reference_legs(bars5)
        cache = {}
        for method,events in by_method.items():
            matrix.extend(dict(r,day=day,method=method) for r in match_legs(bars5,events,legs))
            for event in events:
                for delay in (0,15,60):
                    both = {}
                    for side in (-1,1):
                        key = (event['index'],side,delay)
                        if key not in cache:
                            cache[key] = score(raw,step,closing,event,side,delay)
                        both[side] = cache[key]
                    rows.append({'day':day,'method':method,'delay':delay,'side':event['side'],
                                 'index':event['index'],'r':event['r'],
                                 'decision_Riyadh':event['decision'].astimezone(RIYADH).isoformat(),
                                 'support':event.get('support',[method]),
                                 'candidate':both[event['side']],'up':both[1],'reverse':both[-event['side']]})
    groups = {'older':[s[0] for s in sessions if s[0]<'2026-09-14'],
              'recent':[s[0] for s in sessions if s[0]>='2026-09-14'], 'all':[s[0] for s in sessions]}
    report = {}
    for group,days in groups.items():
        chosen = set(days)
        report[group] = {'sessions':len(days),'methods':{}}
        for method in METHODS:
            selected = [r for r in rows if r['day'] in chosen and r['method']==method]
            zero = [r for r in selected if r['delay']==0]
            report[group]['methods'][method] = {
                'coverage':coverage([r for r in matrix if r['day'] in chosen and r['method']==method],len(zero)),
                'execution':{str(d):summarize([r['candidate'] for r in selected if r['delay']==d]) for d in (0,15,60)},
                'always_up':summarize([r['up'] for r in zero]),
                'reverse':summarize([r['reverse'] for r in zero]),
                'paired_comparison':bootstrap_difference(zero,days)}
        report[group]['complementarity'] = complementarity([r for r in matrix if r['day'] in chosen],METHODS[:3])
    decisions = {}
    for method in ('union','consensus'):
        passed = all(report[g]['methods'][method]['execution']['0']['net_lower']['1']>0 for g in ('older','recent'))
        passed &= report['recent']['methods'][method]['paired_comparison']['paired_session_bootstrap_95'][0]>0
        decisions[method] = 'UNUSED_PROSPECTIVE_TEST_ONLY' if passed else 'SUSPEND_PARAMETERIZATION'
    return {'status':'NOT_READY_RESEARCH_ONLY','decisions':decisions,
            'input_sha256':hashlib.sha256(input_bytes(data)).hexdigest(),
            'protocol_sha256':hashlib.sha256(protocol.read_bytes()).hexdigest(),
            'excluded_sessions':excluded,'report':report,'events':rows,'coverage_matrix':matrix}


if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('opening_validation_raw.json.gz'))
    p.add_argument('--protocol',type=Path,default=Path('ensemble_audit/protocol.json'))
    p.add_argument('--out',type=Path,default=Path('ensemble_audit/results.json.gz'))
    args = p.parse_args()
    result = run(args.data,args.protocol)
    payload = (json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    args.out.write_bytes(gzip.compress(payload,mtime=0) if args.out.suffix=='.gz' else payload)
    print(json.dumps({k:v for k,v in result.items() if k not in ('events','coverage_matrix')},indent=2))
