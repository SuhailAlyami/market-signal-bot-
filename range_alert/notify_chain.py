"""Fallback notification channels, used only after Telegram fails (stdlib only).

Owner rule (2026-11-24): notify through ONE channel, the first that is free, fastest and always on.
The order is:
  1. Telegram (daily_range.send): free, delivers in seconds, permanent.
  2. GitHub issue in this repository: free and permanent, but slower. GitHub then alerts the owner
     through its app and email, depending on the owner's notification settings.
     Needs GITHUB_TOKEN (the workflow's github.token) plus GITHUB_REPOSITORY, and the job needs
     `issues: write`.
  3. Email over SMTP: only when the secrets SMTP_HOST, SMTP_USER, SMTP_PASSWORD and NOTIFY_EMAIL_TO exist
     (for example Gmail with an app password, which is free).
The chain stops at the first channel that delivers, and the remaining channels are never used.
"""
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage


def _title(text):
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), 'Suhail Hunter')
    return ('🔔 ' + first)[:120]


def github_issue(text, env=None, opener=urllib.request.urlopen):
    env = os.environ if env is None else env
    token, repo = env.get('GITHUB_TOKEN'), env.get('GITHUB_REPOSITORY')
    if not token or not repo:
        print('GITHUB_FALLBACK_SKIPPED (no GITHUB_TOKEN/GITHUB_REPOSITORY)')
        return False
    body = text + '\n\n---\nأُرسل عبر GitHub لأن Telegram لم يستقبل الرسالة (قناة احتياطية تلقائية).'
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/issues', method='POST',
        data=json.dumps({'title': _title(text), 'body': body}).encode(),
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                 'User-Agent': 'suhail-hunter-notify'})
    try:
        resp = json.loads(opener(req, timeout=30).read())
        print(f"GITHUB_FALLBACK_OK issue #{resp.get('number')}")
        return bool(resp.get('number'))
    except (urllib.error.HTTPError, OSError, ValueError) as e:
        print(f'GITHUB_FALLBACK_FAILED {type(e).__name__}: {e}')
        return False


def email(text, env=None, smtp_factory=smtplib.SMTP):
    env = os.environ if env is None else env
    host, user, pwd, to = (env.get(k) for k in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'NOTIFY_EMAIL_TO'))
    if not (host and user and pwd and to):
        print('EMAIL_FALLBACK_SKIPPED (SMTP secrets not set)')
        return False
    msg = EmailMessage()
    msg['Subject'], msg['From'], msg['To'] = _title(text), user, to
    msg.set_content(text)
    try:
        with smtp_factory(host, int(env.get('SMTP_PORT') or 587), timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.send_message(msg)
        print('EMAIL_FALLBACK_OK')
        return True
    except (smtplib.SMTPException, OSError) as e:
        print(f'EMAIL_FALLBACK_FAILED {type(e).__name__}: {e}')
        return False


FALLBACKS = (github_issue, email)


def fallback(text):
    """Try the fallback channels in order and return the name of the one that delivered, or None."""
    for channel in FALLBACKS:
        if channel(text):
            sys.stdout.flush()
            return channel.__name__
    return None
