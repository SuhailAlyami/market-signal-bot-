"""Report runtime OAuth availability without exposing credentials or logging in."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path


async def inspect(storage=None):
    from ibkr_mcp_client import PrivateOAuthStorage
    storage=storage or PrivateOAuthStorage()
    report={'source':'IBKR MCP', 'observed_at':datetime.now(timezone.utc).isoformat(),
            'readiness':'NOT_READY', 'feed_realtime_verified':False, 'orders_enabled':False}
    try:
        present=await storage.get_tokens() is not None and await storage.get_client_info() is not None
        report.update(status='AUTH_PRESENT_UNVERIFIED' if present else 'AUTHORIZATION_REQUIRED',
                      runtime_auth_present=present)
    except Exception as exc:
        report.update(status='AUTH_STORAGE_ERROR',runtime_auth_present=False,error_type=type(exc).__name__)
    return report


def run(output):
    report=asyncio.run(inspect())
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as stream:
            stream.write('ready='+str(report['runtime_auth_present']).lower()+'\n')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:
            stream.write('## IBKR runtime authorization\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n')
    print(json.dumps(report))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='.hunter-state/ibkr-runtime.json')
    run(parser.parse_args().output)
