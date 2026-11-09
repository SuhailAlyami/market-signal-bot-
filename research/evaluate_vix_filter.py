import json,runpy,contextlib,io,datetime
from pathlib import Path
from early_metric import score
p=Path(__file__).parent
v=json.loads((p/'vix1000_raw.json').read_text());vs={int(datetime.datetime.fromisoformat(t.replace('Z','+00:00')).timestamp()*1000):float(c) for t,c in zip(v['time'],v['close'])}
with contextlib.redirect_stdout(io.StringIO()):ns=runpy.run_path(str(p/'compare_head_shoulders.py'));ex=runpy.run_path(str(p/'compare_macd.py'))
bs=ns['bs'];models=dict(ns['signals']);models.update(ex['signals']);eligible=[]
for b in bs:eligible.append(all(b.time-k*60000 in vs for k in range(6)))
common={k:[x if eligible[i] else 0 for i,x in enumerate(ds)] for k,ds in models.items()}
filtered={k:[x if eligible[i] and x*(vs[bs[i].time]-vs[bs[i].time-300000])<0 else 0 for i,x in enumerate(ds)] for k,ds in models.items()}
# Common availability domain for signals; event population retains full SPX sample and is not a common-domain recall claim.
out={'status':'POSTHOC_RESEARCH','common_vix_available_bars':sum(eligible),'spx_bars':len(bs),'filter':'SPX long only if completed VIX close below its 5m-earlier close; short only if above. Six contiguous VIX bars required. Same-index bar closes contemporaneously; no freshness/live claim.','common_domain_baseline':score(bs,common),'with_vix':score(bs,filtered),'limits':'Only recent partial overlap. VIX session differs from SPX; no forward filling. Recall denominators still full SPX events; do not compare as common-domain recall. No holdout or 70 percent claim.'}
for section in ['common_domain_baseline','with_vix']:
 for x in out[section]['models'].values():x.pop('matches',None)
(p/'vix_filter_result.json').write_text(json.dumps(out,indent=2));print('available',sum(eligible))
for k in ['v4_impulse','macd_trend_body','macd_trend_rsi','confirmed_divergence']:
 print(k,[(a,out[a]['models'][k]['matched'],out[a]['models'][k]['signals_evaluable']) for a in ['common_domain_baseline','with_vix']])
