"""One-shot historical fetch from Yahoo chart API. Research only: no alerts, no orders, no secrets.
Records request time, response time and source market time for every payload."""
import json, os, time, urllib.request, datetime as dt
OUT = os.environ.get('OUT_DIR', 'out')
os.makedirs(OUT, exist_ok=True)
JOBS = [(s, i, r) for s in ('^GSPC', 'SPY') for i, r in (('1d','max'), ('1h','730d'), ('15m','60d'), ('5m','60d'))]
log = []
for sym, interval, rng in JOBS:
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval={interval}&range={rng}&includePrePost=false'
    req_t = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60)
        body = r.read(); status = r.status
    except Exception as e:
        body = b''; status = repr(e)
    resp_t = dt.datetime.now(dt.timezone.utc).isoformat()
    name = f"{sym.replace('^','')}_{interval}_{rng}.json"
    n = last = None
    if body:
        open(os.path.join(OUT, name), 'wb').write(body)
        try:
            ts = json.loads(body)['chart']['result'][0]['timestamp']; n = len(ts)
            last = dt.datetime.fromtimestamp(ts[-1], dt.timezone.utc).isoformat()
        except Exception as e:
            n = f'parse_error {e!r}'
    log.append({'file': name, 'url': url, 'status': status, 'request_utc': req_t, 'response_utc': resp_t,
                'bars': n, 'last_bar_utc': last, 'classification': 'DELAYED_RESEARCH_ONLY'})
    time.sleep(2)
json.dump(log, open(os.path.join(OUT, 'fetch_log.json'), 'w'), indent=1)
print(json.dumps(log, indent=1))
