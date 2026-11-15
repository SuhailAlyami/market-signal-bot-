"""Daily SHADOW run of TradingAgents (TauricResearch, pinned commit) on SPY. No orders, research only.
Writes one JSON record per session to the data directory; the decision is made before the NYSE open
with data up to the previous close. Models are chosen from what the Groq key can actually serve."""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY = ZoneInfo('America/New_York')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')
TICKER = 'SPY'
DEEP_PREF = ['llama-3.3-70b-versatile', 'openai/gpt-oss-120b', 'qwen/qwen3-32b', 'moonshotai/kimi-k2-instruct']
QUICK_PREF = ['llama-3.1-8b-instant', 'openai/gpt-oss-20b', 'llama-3.3-70b-versatile']


def groq_models():
    req = urllib.request.Request('https://api.groq.com/openai/v1/models',
                                 headers={'Authorization': 'Bearer '+os.environ['GROQ_API_KEY'], 'User-Agent': 'suhail-hunter-shadow'})
    return sorted(m['id'] for m in json.loads(urllib.request.urlopen(req, timeout=20).read())['data'])


def pick(pref, available, override):
    if override:
        return override
    for m in pref:
        if m in available:
            return m
    raise RuntimeError('No preferred Groq model available; available: ' + ', '.join(available))


def main(out_dir, force=False):
    now = datetime.now(timezone.utc)
    today = now.astimezone(NY).date().isoformat()
    if not CAL.is_session(today):
        if not force:
            print('NO_SESSION_TODAY'); return 0
        today = str(CAL.date_to_session(today, direction='next').date())
    out = Path(out_dir)/f'{today}.json'
    if out.exists():
        print('ALREADY_RECORDED', out.name); return 0
    available = groq_models()
    deep = pick(DEEP_PREF, available, os.environ.get('SHADOW_DEEP_MODEL'))
    quick = pick(QUICK_PREF, available, os.environ.get('SHADOW_QUICK_MODEL'))
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(llm_provider='groq', deep_think_llm=deep, quick_think_llm=quick, max_debate_rounds=1,
               max_risk_discuss_rounds=1, llm_max_retries=6, output_language='English')
    t0 = time.time()
    ta = TradingAgentsGraph(selected_analysts=('market', 'news'), config=cfg)
    # trade_date = previous completed session: the agents only see data up to that close.
    prev = str(CAL.previous_session(today).date())
    state, signal = ta.propagate(TICKER, prev)
    rec = {'session': today, 'data_as_of_close': prev, 'ticker': TICKER, 'signal': signal,
           'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'seconds': round(time.time()-t0, 1),
           'deep_model': deep, 'quick_model': quick, 'tradingagents_commit': os.environ.get('TA_COMMIT'),
           'final_trade_decision': str(state.get('final_trade_decision', ''))[:4000],
           'classification': 'SHADOW_RESEARCH_ONLY'}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, ensure_ascii=False)+'\n')
    print(json.dumps({k: rec[k] for k in ('session', 'data_as_of_close', 'signal', 'deep_model', 'quick_model', 'seconds')}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], force='--force' in sys.argv))
