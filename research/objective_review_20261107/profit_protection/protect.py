"""Causal next-bar stop protection on unchanged research entries."""
import argparse
import gzip
import hashlib
import json
import random
import sys
from datetime import datetime,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from objective_review import RIYADH,input_bytes,load_sessions
from wave_capture.run import score,summarize


def protected_score(raw,step,closing,signal,delay):
    original = score(raw,step,closing,signal,signal['side'],delay)
    if original['status']!='SCORED':
        return dict(original)
    result = dict(original)
    at = datetime.fromisoformat(original['entry_Riyadh'])
    side,entry,r = signal['side'],original['entry'],signal['r']
    window = [b for b in raw if at<=b.at<at+timedelta(minutes=30)]
    result.update(gross_low=side*(window[-1].close-entry),gross_high=side*(window[-1].close-entry),
                  exit='time',protection_armed_Riyadh=None)
    floor = -r
    for b in window:
        opening = side*(b.open-entry)
        favorable = b.high-entry if side==1 else entry-b.low
        worst = b.low-entry if side==1 else entry-b.high
        if opening<=floor:
            result.update(gross_low=opening,gross_high=opening,exit='protected_stop_gap' if floor==0 else 'stop_gap')
            break
        if opening>=2*r:
            result.update(gross_low=2*r,gross_high=2*r,exit='target_gap_capped')
            break
        if worst<=floor:
            ambiguous = favorable>=2*r
            result.update(gross_low=floor,gross_high=2*r if ambiguous else floor,
                          exit='ambiguous' if ambiguous else 'protected_stop' if floor==0 else 'stop')
            break
        if favorable>=2*r:
            result.update(gross_low=2*r,gross_high=2*r,exit='target')
            break
        close_at = b.at+timedelta(minutes=step)
        # Activation occurs AFTER this bar. Never infer favorable touch order.
        if floor<0 and close_at.minute%5==0 and side*(b.close-entry)>=r:
            floor = 0
            result['protection_armed_Riyadh'] = close_at.astimezone(RIYADH).isoformat()
    return result


def paired(rows,days,delay):
    daily = {day:0.0 for day in days}
    for row in rows:
        if row['day'] in daily and row['delay']==delay and row['control']['status']=='SCORED':
            daily[row['day']] += row['protected']['gross_low']-row['control']['gross_low']
    values = list(daily.values())
    rng = random.Random(715)
    samples = sorted(sum(rng.choices(values,k=len(values))) for _ in range(1000))
    return {'protected_minus_control_cost1':round(sum(values),3),
            'paired_session_bootstrap95':[round(samples[24],3),round(samples[974],3)]}


def run(data,source,protocol):
    sessions,excluded = load_sessions(data)
    session_map = {s[0]:s for s in sessions}
    archive = json.loads(gzip.decompress(source.read_bytes()))
    if archive['input_sha256']!=hashlib.sha256(input_bytes(data)).hexdigest():
        raise ValueError('Source dataset mismatch')
    rows = []
    for old in archive['events']:
        if old['method']!='consensus':
            continue
        day = old['day']
        _,raw,_,step,closing = session_map[day]
        signal = dict(decision=datetime.fromisoformat(old['decision_Riyadh']),side=old['side'],r=old['r'])
        control = score(raw,step,closing,signal,signal['side'],old['delay'])
        if control!=old['candidate']:
            raise ValueError('Unchanged entry/control failed reproduction '+day)
        protected = protected_score(raw,step,closing,signal,old['delay'])
        rows.append(dict(day=day,delay=old['delay'],side=old['side'],r=old['r'],
                         decision_Riyadh=old['decision_Riyadh'],control=control,protected=protected))
    groups = {'older':[s[0] for s in sessions if s[0]<'2026-09-14'],
              'recent':[s[0] for s in sessions if s[0]>='2026-09-14'],'all':[s[0] for s in sessions]}
    report = {}
    for name,days in groups.items():
        chosen = set(days)
        own = [r for r in rows if r['day'] in chosen]
        report[name] = {'sessions':len(days),'latencies':{}}
        for delay in (0,15,60):
            selected = [r for r in own if r['delay']==delay]
            scored = [r for r in selected if r['control']['status']=='SCORED']
            differences = [r['protected']['gross_low']-r['control']['gross_low'] for r in scored]
            report[name]['latencies'][str(delay)] = {
                'control':summarize([r['control'] for r in selected]),
                'protected':summarize([r['protected'] for r in selected]),
                'paired':paired(own,days,delay),
                'events_improved':sum(v>1e-9 for v in differences),
                'events_worsened':sum(v < -1e-9 for v in differences),
                'events_same':sum(abs(v)<=1e-9 for v in differences),
                'armed':sum(r['protected']['protection_armed_Riyadh'] is not None for r in scored)}
    passes = all(report[g]['latencies']['0']['protected']['net_lower']['1']>0 for g in ('older','recent'))
    passes &= report['recent']['latencies']['0']['paired']['paired_session_bootstrap95'][0]>0
    passes &= report['recent']['latencies']['15']['protected']['net_lower']['1']>=report['recent']['latencies']['15']['control']['net_lower']['1']
    return {'status':'NOT_READY_RESEARCH_ONLY','decision':'UNUSED_PROSPECTIVE_TEST_ONLY' if passes else 'REJECT_EXIT_CHANGE_KEEP_CONTROL_RESEARCH_ONLY',
            'input_sha256':archive['input_sha256'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'protocol_sha256':hashlib.sha256(protocol.read_bytes()).hexdigest(),'excluded_sessions':excluded,
            'report':report,'events':rows}


if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('opening_validation_raw.json.gz'))
    p.add_argument('--source',type=Path,default=Path('ensemble_audit/results.json.gz'))
    p.add_argument('--protocol',type=Path,default=Path('profit_protection/protocol.json'))
    p.add_argument('--out',type=Path,default=Path('profit_protection/results.json.gz'))
    args = p.parse_args()
    result = run(args.data,args.source,args.protocol)
    payload = (json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    args.out.write_bytes(gzip.compress(payload,mtime=0) if args.out.suffix=='.gz' else payload)
    print(json.dumps({k:v for k,v in result.items() if k!='events'},indent=2))
