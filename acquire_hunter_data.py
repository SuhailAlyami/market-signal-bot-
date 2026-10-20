"""Acquire a bounded IBKR native-futures snapshot, no fallback or invented history.

The MCP chart has no arbitrary start/end pagination. A bounded acquisition is
not the old four-week Yahoo study; retained old artifacts keep their provenance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ibkr_market_data import fetch_bars


def acquire(output: Path, weeks: int = 1, probe: bool = False, interval: str = '1m') -> dict:
    if interval not in ('1m','30s'):raise ValueError('one_minute_or_halfminute_only')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    metadata={'observed_at_utc':datetime.now(timezone.utc).isoformat(),
              'source':'IBKR MCP native futures', 'requests':[], 'files':[],
              'requested_weeks':weeks, 'coverage_guaranteed':False,
              'limitation':'Bounded 1000-bar request, no arbitrary historical pagination.'}
    for symbol in ('ES','NQ'):
        request={'symbol':symbol,'step_count':1000,'interval':interval}
        if weeks!=1:
            request['error']='multiweek_history_not_supported_by_exposed_mcp_chart'
        else:
            try:
                bars=fetch_bars(symbol,interval=interval,require_realtime=probe)
                request.update(rows=len(bars), first_bar=bars.index[0].isoformat(),
                               last_bar=bars.index[-1].isoformat(),metadata=dict(bars.attrs))
                if not probe:
                    target=output/(symbol.lower()+'_ibkr_'+interval+'.csv.gz')
                    bars.to_csv(target,compression={'method':'gzip','mtime':0})
                    metadata['files'].append({'path':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
            except Exception as exc:
                request.update(error_type=type(exc).__name__,data_status=getattr(exc,'reason','provider_error'))
        metadata['requests'].append(request)
    (output/'ibkr-acquisition.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--weeks',type=int,default=1)
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('--interval',choices=('1m','30s'),default='1m')
    args=parser.parse_args()
    result=acquire(args.output,args.weeks,args.probe,args.interval)
    print(json.dumps(result))
    raise SystemExit(0 if any(r.get('rows',0) for r in result['requests']) else 1)
