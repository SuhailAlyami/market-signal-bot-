"""Which option-chain source answers from a GitHub runner right now? Prints status per attempt (no data stored)."""
import json, urllib.request, urllib.error
ATTEMPTS = [
    ('cboe_plain', 'https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json', {'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-gamma-radar)'}),
    ('cboe_site_headers', 'https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json',
     {'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-gamma-radar)', 'Accept': 'application/json, text/plain, */*',
      'Origin': 'https://www.cboe.com', 'Referer': 'https://www.cboe.com/'}),
    ('yahoo_options', 'https://query2.finance.yahoo.com/v7/finance/options/%5ESPX', {'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-gamma-radar)'}),
]
for name, url, h in ATTEMPTS:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40)
        body = r.read()
        info = ''
        try:
            d = json.loads(body)
            if 'data' in d: info = f"options={len(d['data'].get('options', []))} ts={d.get('timestamp')}"
            elif 'optionChain' in d:
                res = d['optionChain']['result'][0]; o = res['options'][0]
                info = f"expirations={len(res.get('expirationDates', []))} calls={len(o.get('calls', []))} keys={list(o['calls'][0].keys())[:12] if o.get('calls') else None}"
        except Exception as e: info = f'non-json {e}'
        print('OK', name, r.status, len(body), info)
    except urllib.error.HTTPError as e:
        print('FAIL', name, e.code, e.reason)
    except Exception as e:
        print('FAIL', name, type(e).__name__, e)
