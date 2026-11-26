"""Free-tier LLM fallback chain (stdlib only): Gemini -> Groq -> OpenRouter free models.

Same idea as FreeLLMAPI (route across free providers, move on when one hits its limit) without a server:
it runs inside a GitHub Actions step and uses only the keys present in the environment.

    python agents/llm_chain.py agents/prompts/audit.md < context.txt > audit.md

Keys (any subset; missing providers are skipped):  GEMINI_API_KEY or GOOGLE_API_KEY, GROQ_API_KEY,
OPENROUTER_API_KEY.  Optional model overrides (comma-separated): GEMINI_MODELS, GROQ_MODELS, OPENROUTER_MODELS.
Exit 0 with the answer on stdout, or exit 1 with every attempt listed on stderr. Free tiers only:
OpenRouter models are used only when their listed price is zero.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = {'User-Agent': 'suhail-hunter-llm-chain'}
TIMEOUT = 120
TRIES_PER_PROVIDER = 3

# Free-tier token limits differ a lot; the context is cut to fit each provider (head kept, note appended).
BUDGET = {'gemini': 180_000, 'openrouter': 100_000, 'groq': 24_000}   # characters (~4 chars per token)
GEMINI_DEFAULT = ['gemini-3.5-flash', 'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite']
GROQ_PREF = ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile', 'moonshotai/kimi-k2-instruct-0905',
             'meta-llama/llama-4-scout-17b-16e-instruct', 'qwen/qwen3-32b', 'openai/gpt-oss-20b']
RETRY_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class Skip(Exception):
    """This model or provider cannot answer now; try the next one."""


def http_json(url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={**UA, 'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')[:200]
        raise Skip(f'HTTP {e.code}: {detail}') from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise Skip(f'{type(e).__name__}: {e}') from e


def fit(context, limit):
    if len(context) <= limit:
        return context
    return context[:limit] + '\n\n[... السياق مقطوع ليناسب حد المزوّد المجاني ...]\n'


def env_list(name):
    return [m.strip() for m in os.environ.get(name, '').split(',') if m.strip()]


# ---- providers: each returns (name, key, models(), ask(model, prompt, context)) -------------------------

def gemini_key():
    return os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')


def gemini_ask(model, prompt, context):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    r = http_json(url, {'systemInstruction': {'parts': [{'text': prompt}]},
                        'contents': [{'role': 'user', 'parts': [{'text': context}]}]},
                  {'x-goog-api-key': gemini_key()})
    try:
        return ''.join(p.get('text', '') for p in r['candidates'][0]['content']['parts'])
    except (KeyError, IndexError, TypeError) as e:
        raise Skip(f'no text in Gemini reply: {str(r)[:200]}') from e


def openai_ask(base, key):
    def ask(model, prompt, context):
        r = http_json(base + '/chat/completions',
                      {'model': model, 'temperature': 0.2,
                       'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': context}]},
                      {'Authorization': 'Bearer ' + key})
        try:
            return r['choices'][0]['message']['content'] or ''
        except (KeyError, IndexError, TypeError) as e:
            raise Skip(f'no text in reply: {str(r)[:200]}') from e
    return ask


def groq_models():
    if env_list('GROQ_MODELS'):
        return env_list('GROQ_MODELS')
    try:
        r = http_json('https://api.groq.com/openai/v1/models', headers={'Authorization': 'Bearer ' + os.environ['GROQ_API_KEY']})
        have = {m['id'] for m in r.get('data', [])}
    except Skip:
        return GROQ_PREF
    return [m for m in GROQ_PREF if m in have] or GROQ_PREF


def openrouter_models():
    """Only zero-priced models, largest context first. Listing needs no key."""
    if env_list('OPENROUTER_MODELS'):
        return env_list('OPENROUTER_MODELS')
    r = http_json('https://openrouter.ai/api/v1/models')
    free = [m for m in r.get('data', [])
            if str(m.get('pricing', {}).get('prompt')) in ('0', '0.0')
            and str(m.get('pricing', {}).get('completion')) in ('0', '0.0')
            and 'text' in (m.get('architecture', {}).get('output_modalities') or ['text'])]
    free.sort(key=lambda m: m.get('context_length') or 0, reverse=True)
    return [m['id'] for m in free]


def providers():
    out = []
    if gemini_key():
        out.append(('gemini', lambda: env_list('GEMINI_MODELS') or GEMINI_DEFAULT, gemini_ask))
    if os.environ.get('GROQ_API_KEY'):
        out.append(('groq', groq_models, openai_ask('https://api.groq.com/openai/v1', os.environ['GROQ_API_KEY'])))
    if os.environ.get('OPENROUTER_API_KEY'):
        out.append(('openrouter', openrouter_models,
                    openai_ask('https://openrouter.ai/api/v1', os.environ['OPENROUTER_API_KEY'])))
    return out


def run(prompt, context, sleep=time.sleep):
    """Return (provider, model, text). Raises RuntimeError listing every failed attempt."""
    log = []
    for name, models, ask in providers():
        try:
            candidates = models()[:TRIES_PER_PROVIDER]
        except Skip as e:
            log.append(f'{name}: model list failed ({e})')
            continue
        for model in candidates:
            try:
                text = ask(model, prompt, fit(context, BUDGET[name])).strip()
            except Skip as e:
                log.append(f'{name}/{model}: {e}')
                sleep(2)
                continue
            if text:
                return name, model, text
            log.append(f'{name}/{model}: empty reply')
    if not log:
        log.append('no provider key set (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY)')
    raise RuntimeError('\n'.join(log))


def main(argv):
    if len(argv) != 2:
        print('usage: llm_chain.py PROMPT_FILE < context', file=sys.stderr)
        return 2
    prompt = open(argv[1], encoding='utf-8').read()
    context = sys.stdin.read()
    try:
        name, model, text = run(prompt, context)
    except RuntimeError as e:
        print('ALL_PROVIDERS_FAILED\n' + str(e), file=sys.stderr)
        return 1
    print(f'LLM_CHAIN_USED {name}/{model}', file=sys.stderr)
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
