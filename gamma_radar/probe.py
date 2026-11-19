"""One-off probe: what does CBOE's free delayed SPX option chain contain? Prints structure only."""
import json, urllib.request
url = 'https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-gamma-radar)'})
d = json.loads(urllib.request.urlopen(req, timeout=60).read())
print('top keys', list(d.keys()), 'timestamp', d.get('timestamp'))
data = d['data']
print('data keys', [k for k in data.keys() if k != 'options'])
print({k: data[k] for k in data if k != 'options' and not isinstance(data[k], (list, dict))})
o = data['options']
print('n options', len(o))
for x in o[:3]: print(x)
zero = [x for x in o if x.get('open_interest')]
print('with OI', len(zero), 'with gamma', sum(1 for x in o if x.get('gamma')))
