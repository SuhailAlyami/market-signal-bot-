"""Prior-only realized volatility context; IV must be supplied separately."""
import math,statistics,json,datetime
from pathlib import Path

def realized_volatility(closes,annual_periods=252):
 if len(closes)<3 or annual_periods<=0 or any(not math.isfinite(x) or x<=0 for x in closes):raise ValueError('Need positive finite closes and annualization')
 returns=[math.log(b/a) for a,b in zip(closes,closes[1:])]
 return statistics.stdev(returns)*math.sqrt(annual_periods)

def prior_daily_context(data,decision_date):
 rows=[i for i,t in enumerate(data['time']) if datetime.datetime.fromisoformat(t.replace('Z','+00:00')).date()<decision_date]
 if len(rows)<21:return {'status':'INSUFFICIENT_HISTORY'}
 selected=rows[-21:]
 return {'status':'RESEARCH_ONLY','rv20_annual_decimal':realized_volatility([data['close'][i] for i in selected]),'last_daily_bar':data['time'][selected[-1]],'iv_contract_decimal':None,'iv_status':'MISSING_POINT_IN_TIME_CONTRACT_IV','option_buy_eligible':False}

if __name__=='__main__':
 p=Path(__file__).parent;data=json.loads((p/'spx_daily60_raw.json').read_text());out={str(datetime.date(2026,10,d)):prior_daily_context(data,datetime.date(2026,10,d)) for d in [28,29,30]}
 (p/'volatility_context_results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
