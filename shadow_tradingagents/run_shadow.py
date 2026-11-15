"""Daily SHADOW run of TradingAgents (TauricResearch, pinned commit) on SPY. No orders, research only.
Writes one JSON record per session to the data directory; the decision is made before the NYSE open
with data up to the previous close. Models are chosen from what the Groq key can actually serve."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY = ZoneInfo('America/New_York')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')
TICKER = 'SPY'
# Analysts call tools. Observed failures on the free Groq tier: llama-3.1-8b-instant produced unparsable tool calls
# (400 "Parsing failed", run 43741872315); gpt-oss-20b has an 8000 tokens-per-minute cap, smaller than one analyst
# request (413, run 43742604884). So candidates are probed for their real TPM limit and ranked by it.
EXCLUDE = ('llama-3.1-8b-instant', 'whisper', 'guard', 'tts', 'playai', 'orpheus', 'compound', 'allam', 'prompt-guard')
DEEP_PREF = ['meta-llama/llama-4-maverick-17b-128e-instruct', 'moonshotai/kimi-k2-instruct-0905', 'moonshotai/kimi-k2-instruct',
             'openai/gpt-oss-120b', 'llama-3.3-70b-versatile', 'meta-llama/llama-4-scout-17b-16e-instruct', 'qwen/qwen3-32b']
QUICK_PREF = ['meta-llama/llama-4-scout-17b-16e-instruct', 'llama-3.3-70b-versatile', 'openai/gpt-oss-20b',
              'moonshotai/kimi-k2-instruct-0905', 'moonshotai/kimi-k2-instruct', 'openai/gpt-oss-120b', 'qwen/qwen3-32b']
MIN_TPM = 9000      # one analyst request was 8291 tokens
MAX_ATTEMPTS = 3
API = 'https://api.groq.com/openai/v1'


def _req(path, body=None):
    return urllib.request.Request(API+path, data=None if body is None else json.dumps(body).encode(),
                                  headers={'Authorization': 'Bearer '+os.environ['GROQ_API_KEY'], 'User-Agent': 'suhail-hunter-shadow',
                                           'Content-Type': 'application/json'})


def groq_models():
    return sorted(m['id'] for m in json.loads(urllib.request.urlopen(_req('/models'), timeout=20).read())['data'])


def probe_tpm(model):
    """Tokens-per-minute limit this key has for `model`, from the rate-limit headers of a 1-token request; 0 if unusable."""
    try:
        r = urllib.request.urlopen(_req('/chat/completions', {'model': model, 'max_tokens': 1,
                                                              'messages': [{'role': 'user', 'content': 'ok'}]}), timeout=30)
        return int(r.headers.get('x-ratelimit-limit-tokens') or 0)
    except urllib.error.HTTPError as e:
        return int(e.headers.get('x-ratelimit-limit-tokens') or 0) if e.code == 429 else 0
    except Exception:  # noqa: BLE001
        return 0


def usable(name):
    return not any(x in name for x in EXCLUDE)


def candidates(pref, available, override, tpm=None):
    """Preferred models that are available, ranked: TPM >= MIN_TPM first (higher TPM first), preference order as tiebreak."""
    if override:
        return [override]
    got = [m for m in pref if m in available and usable(m)]
    if tpm is not None:
        got = [m for m in got if tpm.get(m, 0) > 0]
        got.sort(key=lambda m: (tpm[m] < MIN_TPM, -tpm[m], pref.index(m)))
    if not got:
        raise RuntimeError('No usable Groq model; available: ' + ', '.join(available))
    return got


def plan(deep_c, quick_c, n=MAX_ATTEMPTS):
    """(deep, quick) pairs to try in order: rotate the quick model first (it runs the tool-calling analysts)."""
    pairs = []
    for i in range(n):
        pair = (deep_c[min(i // len(quick_c), len(deep_c)-1)], quick_c[i % len(quick_c)])
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def main(out_dir, force=False, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date().isoformat()
    if not CAL.is_session(today):
        if not force:
            print('NO_SESSION_TODAY'); return 0
        today = str(CAL.date_to_session(today, direction='next').date())
    out = Path(out_dir)/f'{today}.json'
    if out.exists():
        print('ALREADY_RECORDED', out.name); return 0
    available = groq_models()
    print('GROQ_MODELS', ' '.join(available), file=sys.stderr)
    tpm = {m: probe_tpm(m) for m in dict.fromkeys(DEEP_PREF+QUICK_PREF) if m in available and usable(m)}
    print('GROQ_TPM', json.dumps(tpm), file=sys.stderr, flush=True)
    pairs = plan(candidates(DEEP_PREF, available, os.environ.get('SHADOW_DEEP_MODEL'), tpm),
                 candidates(QUICK_PREF, available, os.environ.get('SHADOW_QUICK_MODEL'), tpm))
    print('PLAN', json.dumps(pairs), file=sys.stderr, flush=True)
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    # trade_date = previous completed session: the agents only see data up to that close.
    prev = str(CAL.previous_session(today).date())
    failures = []
    for deep, quick in pairs:
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(llm_provider='groq', deep_think_llm=deep, quick_think_llm=quick, max_debate_rounds=1,
                   max_risk_discuss_rounds=1, llm_max_retries=6, output_language='English')
        t0 = time.time()
        try:
            ta = TradingAgentsGraph(selected_analysts=('market', 'news'), config=cfg)
            state, signal = ta.propagate(TICKER, prev)
            break
        except Exception as e:  # noqa: BLE001  (model/tool-call/rate-limit failure: record and try the next pair)
            failures.append({'deep_model': deep, 'quick_model': quick, 'error': f'{type(e).__name__}: {e}'[:500]})
            print('ATTEMPT_FAILED', json.dumps(failures[-1]), file=sys.stderr, flush=True)
    else:
        print('ALL_ATTEMPTS_FAILED', file=sys.stderr)
        return 1
    rec = {'session': today, 'data_as_of_close': prev, 'ticker': TICKER, 'signal': signal,
           'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'seconds': round(time.time()-t0, 1),
           'deep_model': deep, 'quick_model': quick, 'tradingagents_commit': os.environ.get('TA_COMMIT'),
           'failed_attempts': failures, 'groq_tpm': tpm,
           'final_trade_decision': str(state.get('final_trade_decision', ''))[:4000],
           'classification': 'SHADOW_RESEARCH_ONLY'}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, ensure_ascii=False)+'\n')
    print(json.dumps({k: rec[k] for k in ('session', 'data_as_of_close', 'signal', 'deep_model', 'quick_model', 'seconds')}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], force='--force' in sys.argv))
