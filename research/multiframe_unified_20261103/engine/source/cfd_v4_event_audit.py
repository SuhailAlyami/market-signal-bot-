"""Reproducible v4 all-event audit over authorized 1m OHLC CSV.

CSV columns: time (UTC epoch milliseconds),open,high,low,close.
Reports path diagnostics, NOT fills, actual WATCH invalidation P&L or edge.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from cfd_causal_reference import Bar, directions
from cfd_acceleration_v4 import acceleration, AccelerationWatch
from cfd_path_scoring_v2 import outcome


def audit(bars, start_ms=0, end_ms=2**63-1):
    counts = dict(signals=0,target=0,stop=0,ambiguous=0,gap=0,timeout=0,pending=0)
    history, pending, events = [], [], []
    watch = AccelerationWatch()
    previous = None
    for b in bars:
        if previous is not None and b.time <= previous:
            raise ValueError('Input must be strictly chronological; duplicates are not repaired')
        previous = b.time
        history.append(b)
        survivors=[]
        for e in pending:
            result=None
            if b.time != e['expected'] or not b.valid():
                result='gap'
            else:
                if e['steps'] == 0:
                    e['entry']=b.open
                path=outcome(e['direction'],e['entry'],e['atr'],b.open,b.high,b.low)
                e['steps']+=1
                e['expected']=b.time+60000
                if path != 'pending':
                    result=path
                elif e['steps'] >= 10:
                    result='timeout'
            if result:
                counts[result]+=1
                e['result']=result
                e['resolved_at']=b.time+60000
            else:
                survivors.append(e)
        pending=survivors
        valid,_,_=directions(history)
        direction=acceleration(history)
        state_event=watch.step(b,valid,direction)
        decision=b.time+60000
        if state_event in ('UP','DOWN') and start_ms <= decision < end_ms:
            w=history[-31:]
            atr=sum(max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close))
                    for p,c in zip(w[-22:-2],w[-21:-1]))/20
            e=dict(decision_at=decision,direction=watch.side,atr=atr,
                   expected=decision,entry=None,steps=0,result='pending')
            pending.append(e)
            events.append(e)
            counts['signals']+=1
    counts['pending']=len(pending)
    assert counts['signals'] == sum(v for k,v in counts.items() if k!='signals')
    return dict(status='RESEARCH_ONLY',counts=counts,events=events,
                limits='No costs/fills; fixed ATR path diagnostic; no independent edge claim')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('csv_path',type=Path)
    parser.add_argument('--start-ms',type=int,default=0)
    parser.add_argument('--end-ms',type=int,default=2**63-1)
    args=parser.parse_args()
    with args.csv_path.open(newline='') as f:
        bars=[Bar(int(r['time']),*(float(r[k]) for k in ('open','high','low','close')))
              for r in csv.DictReader(f)]
    result=audit(bars,args.start_ms,args.end_ms)
    result['input_sha256']=hashlib.sha256(args.csv_path.read_bytes()).hexdigest()
    result['input_bars']=len(bars)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
