"""Check a same-host session heartbeat; CI success is never live readiness."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from ny_intraday_shadow import session_at


def inspect(path, *, now, max_age_seconds=180):
    if now.tzinfo is None or not 0 < max_age_seconds <= 300:
        raise ValueError('aware_clock_and_bounded_age_required')
    _, market = session_at(now)
    result = {'market_status':market, 'collector_status':'UNVERIFIED',
              'collector_running_verified':False, 'detector_quality':'NOT_READY',
              'orders_enabled':False}
    try:
        heartbeat=json.loads(Path(path).read_text())
        checked=datetime.fromisoformat(heartbeat['checked_at'])
        if checked.tzinfo is None:
            raise ValueError('naive_heartbeat')
        age=(now-checked).total_seconds()
    except (OSError, ValueError, TypeError, KeyError):
        return {**result,'reason':'heartbeat_missing_or_invalid'}
    if not 0 <= age <= max_age_seconds:
        return {**result,'reason':'heartbeat_stale_or_future','heartbeat_age_seconds':age}
    status=heartbeat.get('status')
    observed=(market=='NY_OPEN' and status=='OBSERVED'
              and heartbeat.get('canonical_heartbeat',{}).get('status')=='ok'
              and heartbeat.get('frozen_status')=='NY_OPEN')
    return {**result,'collector_status':status,'checked_at':checked.isoformat(),
            'heartbeat_age_seconds':age,'collector_running_verified':observed,
            'reason':'recent_successful_cycle' if observed else 'no_current_successful_open_session_cycle'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--heartbeat',required=True)
    args=parser.parse_args()
    report=inspect(args.heartbeat,now=datetime.now(timezone.utc))
    print(json.dumps(report))
    # Closed sessions are expected; no field certifies active detection there.
    return int(report['market_status']=='NY_OPEN' and not report['collector_running_verified'])


if __name__=='__main__':
    raise SystemExit(main())
